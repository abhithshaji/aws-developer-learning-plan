"""Amazon ElastiCache (Valkey/Redis) caching integration for product data.

Implements:
1. Cache-Aside Pattern: Product details and search results are retrieved from cache
   first, falling back to DynamoDB on cache misses and caching for 1 hour (3600s)
   or 30 minutes (1800s).
2. Global Secondary Index (GSI) Query Optimization: Category queries target the
   'category-index' GSI with title filtering rather than expensive full-table scans.
3. Cache Invalidation: Changes to product data automatically purge the specific
   product cache and related search cache keys.
4. Fail-Open Architecture: All Redis operations gracefully fail open to DynamoDB
   if the cache is unreachable or cold.
"""
import os
import json
import boto3
import redis
from typing import Optional, Dict, Any, List
from botocore.exceptions import ClientError
from utils.response_utils import decimal_serializer

# Initialize Valkey connection parameters from environment
VALKEY_HOST = os.environ.get('ELASTICACHE_ENDPOINT', os.environ.get('VALKEY_HOST', 'localhost'))
VALKEY_PORT = int(os.environ.get('ELASTICACHE_PORT', os.environ.get('VALKEY_PORT', 6379)))

try:
    valkey_client = redis.Redis(
        host=VALKEY_HOST,
        port=VALKEY_PORT,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2
    )
except Exception:
    valkey_client = None


def get_product_from_dynamodb(product_id: str) :
    """Retrieve product record directly from DynamoDB."""
    table_name = os.environ.get('PRODUCT_TABLE', 'Products')
    region = (
        boto3.session.Session().region_name
        or os.environ.get('AWS_REGION')
        or os.environ.get('AWS_DEFAULT_REGION')
        or 'us-east-1'
    )
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    try:
        response = table.get_item(Key={'id': product_id})
        return response.get('Item')
    except ClientError as e:
        print(f"DynamoDB error: {e}")
        return None


def get_product_with_cache(
    product_id: str,
) :
    """Retrieve product using the Cache-Aside pattern.
    
    1. Try cache (Valkey/Redis) first.
    2. On cache hit, deserialize and return product.
    3. On cache miss or Valkey error, query DynamoDB.
    4. On successful DynamoDB read, populate cache with 1-hour TTL.
    """
    cache_key = f"product:{product_id}"
    
    
    # 1. Try cache first if client is available
    if valkey_client:
        try:
            cached_product = valkey_client.get(cache_key)
            if cached_product:
                print(f"Cache hit for product {product_id}")
                return json.loads(cached_product)
        except redis.RedisError as e:
            print(f"Valkey error: {e}")
            # Fallback to database if cache fails
            return get_product_from_dynamodb(product_id)

    # 2. Cache miss - get from DynamoDB
    print(f"Cache miss for product {product_id}")
    product = get_product_from_dynamodb(product_id)
    
    # 3. Store in cache with 1 hour (3600s) TTL
    if product and valkey_client:
        try:
            valkey_client.setex(
                cache_key,
                3600,
                json.dumps(product, default=decimal_serializer)
            )
        except redis.RedisError as e:
            print(f"Valkey error writing cache: {e}")
            
    return product


def perform_product_search(
    query: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 20
) :
    """Search products using GSI for categories or fallback scan when category is omitted."""
    table_name = os.environ.get('PRODUCT_TABLE', 'Products')
    region = (
        boto3.session.Session().region_name
        or os.environ.get('AWS_REGION')
        or os.environ.get('AWS_DEFAULT_REGION')
        or 'us-east-1'
    )
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    try:
        if category:
            # Query using category-index GSI
            kwargs = {
                'IndexName': 'category-index',
                'KeyConditionExpression': 'category = :category',
                'ExpressionAttributeValues': {':category': category},
                'Limit': limit
            }
            if query:
                kwargs['FilterExpression'] = 'contains(#title, :query)'
                kwargs['ExpressionAttributeNames'] = {'#title': 'title'}
                kwargs['ExpressionAttributeValues'][':query'] = query
                
            response = table.query(**kwargs)
            return response.get('Items', [])
        else:
            # Fallback scan across table when no category partition key is specified
            kwargs = {'Limit': limit}
            if query:
                kwargs['FilterExpression'] = 'contains(#title, :query)'
                kwargs['ExpressionAttributeNames'] = {'#title': 'title'}
                kwargs['ExpressionAttributeValues'] = {':query': query}
            response = table.scan(**kwargs)
            return response.get('Items', [])
            
    except ClientError as e:
        print(f"Search error: {e}")
        print("WARNING: Ensure GSI indexes are properly configured")
        return []


def search_products_with_cache(
    query: Optional[str] = None,
    category: Optional[str] = None,
    page: int = 1,
    limit: int = 20,
) :
    """Search products with Valkey caching (30-minute TTL)."""
    cache_key = f"search:{query}:{category}:{page}:{limit}"
   
    
    try:
        # Check cache first
        if valkey_client:
            cached_results = valkey_client.get(cache_key)
            if cached_results:
                print(f"Cache hit for search: {query}")
                return json.loads(cached_results)
        
        # Cache miss - perform search
        print(f"Cache miss for search: {query}")
        results = perform_product_search(query, category, page, limit)
        
        if results and valkey_client:
            # Cache search results for 30 minutes (1800s)
            valkey_client.setex(
                cache_key,
                1800,
                json.dumps(results, default=decimal_serializer)
            )
        
        return results
        
    except redis.RedisError as e:
        print(f"Valkey error during search: {e}")
        # Fallback to direct search
        return perform_product_search(query, category, page, limit)


def invalidate_product_cache(
    product_id: str,
    category: Optional[str] = None,
):
    """Invalidate product and related search result cache entries."""
    if not valkey_client:
        return
        
    try:
        # Remove specific product from cache
        product_cache_key = f"product:{product_id}"
        valkey_client.delete(product_cache_key)
        
        # Invalidate search results that might include this product
        if category:
            # Remove category-specific searches
            pattern = f"search:*:{category}:*"
            for key in valkey_client.scan_iter(match=pattern):
                valkey_client.delete(key)
        
        # Remove general search results
        pattern = "search:*"
        for key in valkey_client.scan_iter(match=pattern):
            valkey_client.delete(key)
            
        print(f"Cache invalidated for product {product_id}")
        
    except redis.RedisError as e:
        print(f"Cache invalidation error: {e}")


def update_product_with_cache_invalidation(
    product_id: str,
    updates: Dict[str, Any],
) :
    """Update product in DynamoDB and invalidate all related cache entries."""
    table_name = os.environ.get('PRODUCT_TABLE', 'Products')
    region = (
        boto3.session.Session().region_name
        or os.environ.get('AWS_REGION')
        or os.environ.get('AWS_DEFAULT_REGION')
        or 'us-east-1'
    )
    dynamodb = boto3.resource('dynamodb', region_name=region)
    table = dynamodb.Table(table_name)
    
    try:
        # Update product in DynamoDB
        response = table.update_item(
            Key={'id': product_id},
            UpdateExpression='SET #title = :title, #price = :price, #description = :description',
            ExpressionAttributeNames={
                '#title': 'title',
                '#price': 'price',
                '#description': 'description'
            },
            ExpressionAttributeValues={
                ':title': updates['title'],
                ':price': updates['price'],
                ':description': updates['description']
            },
            ReturnValues='ALL_NEW'
        )
        
        # Invalidate related cache entries
        invalidate_product_cache(product_id, updates.get('category'))
        
        return response.get('Attributes')
        
    except ClientError as e:
        print(f"Update error: {e}")
        return None


# TTL strategies for different data types
CACHE_TTL = {
    'product_details': 3600,      # 1 hour - products change infrequently
    'search_results': 1800,       # 30 minutes - balance freshness and performance
    'category_lists': 7200,       # 2 hours - categories change rarely
    'inventory_counts': 300,      # 5 minutes - inventory changes frequently
    'user_sessions': 86400,       # 24 hours - maintain user state
    'popular_products': 3600      # 1 hour - trending items change moderately
}


def cache_with_appropriate_ttl(key: str, data: Any, data_type: str):
    """Store data in cache using data-type specific TTL strategy."""
    ttl = CACHE_TTL.get(data_type, 3600)  # Default to 1 hour
    
    if not valkey_client:
        return
        
    try:
        valkey_client.setex(key, ttl, json.dumps(data, default=decimal_serializer))
        print(f"Cached {key} with TTL {ttl} seconds")
    except redis.RedisError as e:
        print(f"Caching error: {e}")


def get_comprehensive_cache_stats() -> Optional[Dict[str, Any]]:
    """Retrieve comprehensive cache performance, memory, and eviction statistics."""
    if not valkey_client:
        return None
        
    try:
        info = valkey_client.info()
        
        stats = {
            # Performance metrics
            'hits': info.get('keyspace_hits', 0),
            'misses': info.get('keyspace_misses', 0),
            'hit_rate': 0,
            
            # Memory metrics
            'memory_used': info.get('used_memory', 0),
            'memory_used_human': info.get('used_memory_human', '0B'),
            'memory_max': info.get('maxmemory', 0),
            'memory_utilization': 0,
            
            # Eviction metrics
            'evicted_keys': info.get('evicted_keys', 0),
            'expired_keys': info.get('expired_keys', 0),
            
            # Connection metrics
            'connected_clients': info.get('connected_clients', 0),
            'total_connections_received': info.get('total_connections_received', 0),
            
            # Performance metrics
            'instantaneous_ops_per_sec': info.get('instantaneous_ops_per_sec', 0),
            'total_commands_processed': info.get('total_commands_processed', 0)
        }
        
        # Calculate derived metrics
        total_requests = stats['hits'] + stats['misses']
        if total_requests > 0:
            stats['hit_rate'] = (stats['hits'] / total_requests) * 100
        
        if stats['memory_max'] > 0:
            stats['memory_utilization'] = (stats['memory_used'] / stats['memory_max']) * 100
        
        return stats
        
    except redis.RedisError as e:
        print(f"Error getting cache stats: {e}")
        return None


def analyze_cache_performance() -> Optional[Dict[str, Any]]:
    """Analyze and log cache performance, hit rate, memory health, and evictions."""
    stats = get_comprehensive_cache_stats()
    if not stats:
        return None
    
    print("=== Cache Performance Analysis ===")
    
    # Hit rate analysis
    hit_rate = stats['hit_rate']
    if hit_rate >= 90:
        print(f"Excellent hit rate: {hit_rate:.2f}%")
    elif hit_rate >= 70:
        print(f"Good hit rate: {hit_rate:.2f}% (consider optimizing TTL)")
    else:
        print(f"Poor hit rate: {hit_rate:.2f}% (review caching strategy)")
    
    # Memory utilization analysis
    memory_util = stats['memory_utilization']
    if memory_util >= 80:
        print(f"High memory usage: {memory_util:.1f}% (risk of evictions)")
    elif memory_util >= 60:
        print(f"Moderate memory usage: {memory_util:.1f}%")
    else:
        print(f"Low memory usage: {memory_util:.1f}% (good headroom)")
    
    # Operations analysis
    ops_per_sec = stats['instantaneous_ops_per_sec']
    print(f"Current operations: {ops_per_sec} ops/sec")
    print(f"Total commands: {stats['total_commands_processed']:,}")
    print(f"Connected clients: {stats['connected_clients']}")
    
    # Eviction analysis
    evicted = stats['evicted_keys']
    if evicted > 0:
        print(f"Evicted keys: {evicted:,} (consider increasing memory)")
    
    return stats
