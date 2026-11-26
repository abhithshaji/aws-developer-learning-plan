import unittest
from unittest.mock import MagicMock, patch

from utils.sqs_monitoring import monitor_queue_metrics, scale_processing_capacity


class TestSQSMonitoring(unittest.TestCase):

    @patch("utils.sqs_monitoring.boto3.client")
    def test_monitor_queue_metrics_with_datapoints(self, mock_boto_client):
        """Test monitoring extracts SQS attributes and CloudWatch statistics."""
        mock_cw = MagicMock()
        mock_sqs = MagicMock()

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "42",
                "ApproximateNumberOfMessagesNotVisible": "5",
            }
        }
        mock_cw.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Average": 20.0, "Maximum": 35.0},
                {"Average": 38.0, "Maximum": 60.0},
            ]
        }

        def client_factory(service_name):
            return mock_cw if service_name == "cloudwatch" else mock_sqs

        mock_boto_client.side_effect = client_factory

        metrics = monitor_queue_metrics(
            "https://sqs.us-east-1.amazonaws.com/123456789012/order-processing-queue"
        )

        self.assertEqual(metrics["visible_messages"], 42)
        self.assertEqual(metrics["in_flight_messages"], 5)
        self.assertEqual(metrics["average_queue_depth"], 38.0)
        self.assertEqual(metrics["max_queue_depth"], 60.0)

    @patch("utils.sqs_monitoring.boto3.client")
    def test_monitor_queue_metrics_empty_datapoints(self, mock_boto_client):
        """Test monitoring returns 0 defaults when CloudWatch has no datapoints."""
        mock_cw = MagicMock()
        mock_sqs = MagicMock()

        mock_sqs.get_queue_attributes.return_value = {
            "Attributes": {
                "ApproximateNumberOfMessages": "0",
                "ApproximateNumberOfMessagesNotVisible": "0",
            }
        }
        mock_cw.get_metric_statistics.return_value = {"Datapoints": []}
        mock_boto_client.side_effect = lambda svc: mock_cw if svc == "cloudwatch" else mock_sqs

        metrics = monitor_queue_metrics("https://sqs.example.com/123/order-processing-queue")

        self.assertEqual(metrics["visible_messages"], 0)
        self.assertEqual(metrics["in_flight_messages"], 0)
        self.assertEqual(metrics["average_queue_depth"], 0)
        self.assertEqual(metrics["max_queue_depth"], 0)

    def test_scale_processing_capacity_scale_up(self):
        """Test high queue depth recommends scaling up, capped at 50."""
        res = scale_processing_capacity({"visible_messages": 250, "max_queue_depth": 250})
        self.assertEqual(len(res["recommendations"]), 1)
        rec = res["recommendations"][0]
        self.assertEqual(rec["action"], "scale_up")
        self.assertEqual(rec["suggested_capacity"], 25)

        capped = scale_processing_capacity({"visible_messages": 1000, "max_queue_depth": 1000})
        self.assertEqual(capped["recommendations"][0]["suggested_capacity"], 50)

    def test_scale_processing_capacity_scale_down(self):
        """Test consistently low queue utilization recommends scaling down."""
        res = scale_processing_capacity({"visible_messages": 3, "max_queue_depth": 2})
        self.assertEqual(len(res["recommendations"]), 1)
        rec = res["recommendations"][0]
        self.assertEqual(rec["action"], "scale_down")
        self.assertEqual(rec["suggested_capacity"], 2)

    def test_scale_processing_capacity_steady_state(self):
        """Test normal queue utilization produces no scaling recommendations."""
        res = scale_processing_capacity({"visible_messages": 40, "max_queue_depth": 45})
        self.assertEqual(res["recommendations"], [])


if __name__ == "__main__":
    unittest.main()
