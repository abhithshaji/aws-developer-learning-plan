import os

# Set mock AWS credentials before any boto3 import
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["AWS_SECURITY_TOKEN"] = "testing"
os.environ["AWS_SESSION_TOKEN"] = "testing"
os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
os.environ["PRODUCT_TABLE"] = "Products"

import json
import unittest
from unittest.mock import MagicMock, patch
from decimal import Decimal
import redis
from moto import mock_aws
import boto3
from db.cache_db import (
    get_product_with_cache,
    get_product_from_dynamodb,
    perform_product_search,
    search_products_with_cache,
    invalidate_product_cache,
    update_product_with_cache_invalidation,
    cache_with_appropriate_ttl,
    get_comprehensive_cache_stats,
    analyze_cache_performance,
    CACHE_TTL
)


class TestCacheDB(unittest.TestCase):
    """Test suite for Valkey/Redis Cache-Aside pattern, GSI search, and cache invalidation."""

    def setUp(self):
        self.table_name = "Products"
        os.environ["PRODUCT_TABLE"] = self.table_name

    @mock_aws
    def _create_mock_table(self):
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        table = dynamodb.create_table(
            TableName=self.table_name,
            KeySchema=[{'AttributeName': 'id', 'KeyType': 'HASH'}],
            AttributeDefinitions=[
                {'AttributeName': 'id', 'AttributeType': 'S'},
                {'AttributeName': 'category', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[{
                'IndexName': 'category-index',
                'KeySchema': [{'AttributeName': 'category', 'KeyType': 'HASH'}],
                'Projection': {'ProjectionType': 'ALL'}
            }],
            BillingMode='PAY_PER_REQUEST'
        )
        return dynamodb, table

    def test_cache_hit_returns_cached_item_without_db_query(self):
        """Test cache hit: returns cached product immediately without calling DynamoDB."""
        mock_redis = MagicMock()
        mock_redis.get.return_value = json.dumps({
            'id': 'prod_001',
            'title': 'Wireless Headphones',
            'price': 199.99
        })

        with patch('db.cache_db.valkey_client', mock_redis):
            with patch('db.cache_db.get_product_from_dynamodb') as mock_db:
                result = get_product_with_cache('prod_001')

                self.assertIsNotNone(result)
                self.assertEqual(result['id'], 'prod_001')
                self.assertEqual(result['title'], 'Wireless Headphones')
                mock_redis.get.assert_called_once_with('product:prod_001')
                mock_db.assert_not_called()

    @mock_aws
    def test_cache_miss_queries_dynamodb_and_populates_cache(self):
        """Test cache miss: reads item from DynamoDB and populates Valkey cache with 1h TTL."""
        _, table = self._create_mock_table()
        table.put_item(Item={
            'id': 'prod_002',
            'title': 'USB-C Cable',
            'category': 'Electronics',
            'price': Decimal('12.99')
        })

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Cache miss

        with patch('db.cache_db.valkey_client', mock_redis):
            result = get_product_with_cache('prod_002')

            self.assertIsNotNone(result)
            self.assertEqual(result['id'], 'prod_002')
            self.assertEqual(result['title'], 'USB-C Cable')

            # Verify setex was called with 1 hour (3600s) TTL
            mock_redis.get.assert_called_once_with('product:prod_002')
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            self.assertEqual(call_args[0], 'product:prod_002')
            self.assertEqual(call_args[1], 3600)
            cached_data = json.loads(call_args[2])
            self.assertEqual(cached_data['id'], 'prod_002')
            self.assertEqual(cached_data['price'], 12.99)

    @mock_aws
    def test_valkey_error_falls_back_to_dynamodb(self):
        """Test resilience: RedisError fails open to DynamoDB without crashing."""
        _, table = self._create_mock_table()
        table.put_item(Item={
            'id': 'prod_003',
            'title': 'Ceramic Mug',
            'category': 'Home',
            'price': Decimal('8.49')
        })

        mock_redis = MagicMock()
        mock_redis.get.side_effect = redis.RedisError("Valkey cluster connection timeout")

        with patch('db.cache_db.valkey_client', mock_redis):
            result = get_product_with_cache('prod_003')

            self.assertIsNotNone(result)
            self.assertEqual(result['id'], 'prod_003')
            self.assertEqual(result['title'], 'Ceramic Mug')

    @mock_aws
    def test_get_product_from_dynamodb_direct(self):
        """Test direct DynamoDB retrieval function."""
        _, table = self._create_mock_table()
        table.put_item(Item={'id': 'prod_004', 'title': 'Keyboard', 'category': 'Electronics'})

        result = get_product_from_dynamodb('prod_004')
        self.assertIsNotNone(result)
        self.assertEqual(result['title'], 'Keyboard')

        none_result = get_product_from_dynamodb('prod_nonexistent')
        self.assertIsNone(none_result)

    @mock_aws
    def test_search_products_with_cache_hit(self):
        """Test search cache hit: returns cached results without querying GSI."""
        mock_redis = MagicMock()
        cached_items = [{'id': 'prod_001', 'title': 'Wireless Headphones'}]
        mock_redis.get.return_value = json.dumps(cached_items)

        with patch('db.cache_db.valkey_client', mock_redis):
            with patch('db.cache_db.perform_product_search') as mock_search:
                results = search_products_with_cache(
                    query='Headphones',
                    category='Electronics'
                )
                self.assertEqual(len(results), 1)
                self.assertEqual(results[0]['title'], 'Wireless Headphones')
                mock_redis.get.assert_called_once_with('search:Headphones:Electronics:1:20')
                mock_search.assert_not_called()

    @mock_aws
    def test_search_products_cache_miss_uses_gsi_and_populates_cache(self):
        """Test search cache miss: queries category-index GSI and saves results with 30m TTL."""
        _, table = self._create_mock_table()
        table.put_item(Item={
            'id': 'prod_010',
            'title': 'Gaming Headphones Pro',
            'category': 'Electronics',
            'price': Decimal('149.99')
        })
        table.put_item(Item={
            'id': 'prod_011',
            'title': 'USB Hub',
            'category': 'Electronics',
            'price': Decimal('29.99')
        })

        mock_redis = MagicMock()
        mock_redis.get.return_value = None  # Cache miss

        with patch('db.cache_db.valkey_client', mock_redis):
            results = search_products_with_cache(
                query='Headphones',
                category='Electronics'
            )

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['title'], 'Gaming Headphones Pro')

            # Verify cached with 1800s (30m) TTL
            mock_redis.setex.assert_called_once()
            call_args = mock_redis.setex.call_args[0]
            self.assertEqual(call_args[0], 'search:Headphones:Electronics:1:20')
            self.assertEqual(call_args[1], 1800)

    @mock_aws
    def test_search_products_valkey_error_fallback(self):
        """Test search fallback to DynamoDB when Valkey errors out."""
        _, table = self._create_mock_table()
        table.put_item(Item={
            'id': 'prod_012',
            'title': 'Bluetooth Speaker',
            'category': 'Audio',
            'price': Decimal('59.99')
        })

        mock_redis = MagicMock()
        mock_redis.get.side_effect = redis.RedisError("Connection reset")

        with patch('db.cache_db.valkey_client', mock_redis):
            results = search_products_with_cache(
                query='Speaker',
                category='Audio'
            )
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['title'], 'Bluetooth Speaker')

    def test_invalidate_product_cache(self):
        """Test cache invalidation purges product key and scans for search patterns."""
        mock_redis = MagicMock()
        mock_redis.scan_iter.side_effect = [
            ['search:test:Electronics:1:20'],  # category match
            ['search:test:None:1:20']          # general match
        ]

        with patch('db.cache_db.valkey_client', mock_redis):
            invalidate_product_cache('prod_001', category='Electronics')

            # Verify product cache key deleted
            mock_redis.delete.assert_any_call('product:prod_001')
            mock_redis.delete.assert_any_call('search:test:Electronics:1:20')
            mock_redis.delete.assert_any_call('search:test:None:1:20')

    @mock_aws
    def test_update_product_with_cache_invalidation(self):
        """Test updating DynamoDB product and invalidating cache keys."""
        _, table = self._create_mock_table()
        table.put_item(Item={
            'id': 'prod_020',
            'title': 'Old Title',
            'category': 'Electronics',
            'price': Decimal('99.99'),
            'description': 'Old Description'
        })

        mock_redis = MagicMock()
        mock_redis.scan_iter.return_value = []

        updates = {
            'title': 'New Super Title',
            'price': Decimal('119.99'),
            'description': 'Updated Description',
            'category': 'Electronics'
        }

        with patch('db.cache_db.valkey_client', mock_redis):
            updated_attrs = update_product_with_cache_invalidation(
                'prod_020',
                updates
            )

            self.assertIsNotNone(updated_attrs)
            self.assertEqual(updated_attrs['title'], 'New Super Title')
            self.assertEqual(updated_attrs['price'], Decimal('119.99'))

            # Verify DynamoDB record updated
            item = table.get_item(Key={'id': 'prod_020'}).get('Item')
            self.assertEqual(item['title'], 'New Super Title')

            # Verify invalidation occurred
            mock_redis.delete.assert_any_call('product:prod_020')

    def test_cache_with_appropriate_ttl(self):
        """Test TTL strategies apply correct expiration for different data types."""
        mock_redis = MagicMock()
        with patch('db.cache_db.valkey_client', mock_redis):
            # 1. Inventory counts: 300s
            cache_with_appropriate_ttl('inv:prod_001', {'stock': 42}, 'inventory_counts')
            mock_redis.setex.assert_called_with('inv:prod_001', 300, '{"stock": 42}')

            # 2. Category lists: 7200s
            cache_with_appropriate_ttl('cats:all', ['Electronics'], 'category_lists')
            mock_redis.setex.assert_called_with('cats:all', 7200, '["Electronics"]')

            # 3. Default fallback: 3600s
            cache_with_appropriate_ttl('unknown:data', {'data': 1}, 'unknown_type')
            mock_redis.setex.assert_called_with('unknown:data', 3600, '{"data": 1}')

    def test_get_comprehensive_cache_stats(self):
        """Test calculation of hit rate and memory utilization from Redis info."""
        mock_redis = MagicMock()
        mock_redis.info.return_value = {
            'keyspace_hits': 90,
            'keyspace_misses': 10,
            'used_memory': 600,
            'used_memory_human': '600B',
            'maxmemory': 1000,
            'evicted_keys': 2,
            'expired_keys': 15,
            'connected_clients': 3,
            'total_connections_received': 50,
            'instantaneous_ops_per_sec': 120,
            'total_commands_processed': 5000
        }

        with patch('db.cache_db.valkey_client', mock_redis):
            stats = get_comprehensive_cache_stats()

            self.assertIsNotNone(stats)
            self.assertEqual(stats['hits'], 90)
            self.assertEqual(stats['misses'], 10)
            self.assertEqual(stats['hit_rate'], 90.0)
            self.assertEqual(stats['memory_utilization'], 60.0)
            self.assertEqual(stats['evicted_keys'], 2)

    def test_analyze_cache_performance(self):
        """Test analyze_cache_performance executes and returns stats dictionary."""
        mock_stats = {
            'hit_rate': 95.0,
            'memory_utilization': 50.0,
            'instantaneous_ops_per_sec': 250,
            'total_commands_processed': 10000,
            'connected_clients': 4,
            'evicted_keys': 0
        }

        with patch('db.cache_db.get_comprehensive_cache_stats', return_value=mock_stats):
            stats = analyze_cache_performance()
            self.assertIsNotNone(stats)
            self.assertEqual(stats['hit_rate'], 95.0)


if __name__ == '__main__':
    unittest.main()
