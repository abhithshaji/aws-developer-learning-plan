import unittest
from unittest.mock import MagicMock, patch
import utils.elasticache_setup
from utils.elasticache_setup import create_elasticache_cluster


class TestElastiCacheSetup(unittest.TestCase):
    """Test suite for ElastiCache cluster creation utilities."""

    def test_create_valkey_cluster_success(self):
        """Test creating a Valkey cluster with port 6379."""
        mock_client = MagicMock()
        mock_client.create_cache_cluster.return_value = {
            'CacheCluster': {
                'CacheClusterId': 'online-store-valkey-cache',
                'CacheNodes': [
                    {'Endpoint': {'Address': 'valkey.123456.cache.amazonaws.com'}}
                ]
            }
        }

        with patch('utils.elasticache_setup.elasticache_client', mock_client):
            endpoint = create_elasticache_cluster(engine='valkey')

            self.assertEqual(endpoint, 'valkey.123456.cache.amazonaws.com')
            mock_client.create_cache_cluster.assert_called_once()
            _, kwargs = mock_client.create_cache_cluster.call_args
            self.assertEqual(kwargs['Port'], 6379)
            self.assertEqual(kwargs['Engine'], 'valkey')

    def test_create_memcached_cluster_success(self):
        """Test creating a Memcached cluster with port 11211."""
        mock_client = MagicMock()
        mock_client.create_cache_cluster.return_value = {
            'CacheCluster': {
                'CacheClusterId': 'online-store-memcached-cache',
                'ConfigurationEndpoint': {'Address': 'memcached.123456.cache.amazonaws.com'}
            }
        }

        with patch('utils.elasticache_setup.elasticache_client', mock_client):
            endpoint = create_elasticache_cluster(engine='memcached')

            self.assertEqual(endpoint, 'memcached.123456.cache.amazonaws.com')
            _, kwargs = mock_client.create_cache_cluster.call_args
            self.assertEqual(kwargs['Port'], 11211)
            self.assertEqual(kwargs['Engine'], 'memcached')

    def test_create_cluster_error_handling(self):
        """Test graceful error handling when cluster creation fails."""
        mock_client = MagicMock()
        mock_client.create_cache_cluster.side_effect = Exception("AWS ElastiCache Quota Exceeded")

        with patch('utils.elasticache_setup.elasticache_client', mock_client):
            endpoint = create_elasticache_cluster(engine='valkey')

            self.assertIsNone(endpoint)


if __name__ == '__main__':
    unittest.main()
