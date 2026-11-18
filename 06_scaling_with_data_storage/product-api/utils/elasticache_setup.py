"""Amazon ElastiCache / Valkey cluster provisioning and configuration utilities.

Provides functions to create and manage in-memory caching clusters for the online store API.
Supports Valkey, Redis, and Memcached engines.
"""
import os
import boto3
from typing import Optional, List

try:
    elasticache_client = boto3.client('elasticache')
except Exception:
    elasticache_client = None


def create_elasticache_cluster(engine: str = 'valkey'):
    
    # Engine options: 'valkey', 'redis', 'memcached'
    port = 6379 if engine.lower() in ['valkey', 'redis'] else 11211
    
    # Resolve network configuration
    subnet_group = (
         os.environ.get('CACHE_SUBNET_GROUP')
        or 'your-subnet-group'
    )
    security_groups = (
         ([os.environ['CACHE_SECURITY_GROUP']] if 'CACHE_SECURITY_GROUP' in os.environ else ['your-security-group-id'])
    )

    target_cluster_id = f'online-store-{engine.lower()}-cache'

    # COST WARNING: ElastiCache instances incur costs while running.
    # If this is for testing only, remove the instance when not in use.
    try:
        kwargs = {
            'CacheClusterId': target_cluster_id,
            'CacheNodeType': 'cache.t3.micro',  # Start small - can scale up later
            'Engine': engine,
            'NumCacheNodes': 1,
            'Port': port,
        }
        if subnet_group:
            kwargs['CacheSubnetGroupName'] = subnet_group
        if security_groups:
            kwargs['SecurityGroupIds'] = security_groups

        response = elasticache_client.create_cache_cluster(**kwargs)
        print(f"ElastiCache {engine} cluster '{target_cluster_id}' created successfully")
        
        cluster = response.get('CacheCluster', {})
        
        # Return appropriate endpoint based on engine
        if engine == 'memcached':
            config_endpoint = cluster.get('ConfigurationEndpoint', {})
            return config_endpoint.get('Address')
        else:
            # Node endpoints populate once the cluster status is 'available'
            cache_nodes = cluster.get('CacheNodes', [])
            if cache_nodes and 'Endpoint' in cache_nodes[0]:
                return cache_nodes[0]['Endpoint'].get('Address')
            return target_cluster_id
            
    except Exception as e:
        print(f"Error creating {engine} cluster: {e}")
        return None
