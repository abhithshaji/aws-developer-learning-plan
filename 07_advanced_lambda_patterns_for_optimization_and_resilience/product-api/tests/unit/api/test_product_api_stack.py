import aws_cdk as core
import aws_cdk.assertions as assertions
from product_api.product_api_stack import ProductApiStack

def test_sqs_queue_created():
    """Verify CDK synthesizes the Dead-Letter SQS Queue with expected properties."""
    app = core.App()
    stack = ProductApiStack(app, "product-api")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::SQS::Queue", {
        "VisibilityTimeout": 300,
        "MessageRetentionPeriod": 1209600
    })

def test_s3_bucket_created():
    """Verify CDK synthesizes the S3 Product Images Bucket with versioning."""
    app = core.App()
    stack = ProductApiStack(app, "product-api")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::S3::Bucket", {
        "VersioningConfiguration": {
            "Status": "Enabled"
        }
    })

def test_product_utilities_layer_created():
    """Verify CDK synthesizes the ProductUtilitiesLayer with compatible runtimes."""
    app = core.App()
    stack = ProductApiStack(app, "product-api")
    template = assertions.Template.from_stack(stack)

    template.has_resource_properties("AWS::Lambda::LayerVersion", {
        "Description": "v1.0.0 - Shared validation, database helpers, and response formatting",
        "CompatibleRuntimes": ["python3.13"]
    })

