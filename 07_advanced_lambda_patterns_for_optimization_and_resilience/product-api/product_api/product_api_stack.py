from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_dynamodb,
    aws_lambda,
    aws_apigateway as apigw,
    aws_sqs as sqs,
    aws_s3 as s3,
    aws_s3_notifications as s3n
)

class ProductApiStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # 1. DynamoDB table for the product catalog
        products_table = aws_dynamodb.Table(
            self, "ProductsTable",
            table_name="Products",
            partition_key=aws_dynamodb.Attribute(name="id", type=aws_dynamodb.AttributeType.STRING),
            billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST
        )

        # Secondary index for category queries
        products_table.add_global_secondary_index(
            index_name="category-index",
            partition_key=aws_dynamodb.Attribute(name="category", type=aws_dynamodb.AttributeType.STRING)
        )

        # 2. S3 Bucket for Product Images
        image_bucket = s3.Bucket(
            self, "ProductImagesBucket",
            versioned=True,
            block_public_access=s3.BlockPublicAccess(
                block_public_acls=True,
                ignore_public_acls=True,
                block_public_policy=False,
                restrict_public_buckets=False
            ),
            cors=[
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.GET, s3.HttpMethods.PUT, s3.HttpMethods.POST],
                    allowed_origins=["*"],
                    allowed_headers=["*"],
                    max_age=3600
                )
            ],
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        # Lambda configuration
        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = aws_lambda.Code.from_asset(
            ".",
            exclude=[".venv", "venv", "cdk.out", ".git", "tests", "__pycache__"]
        )

        common_env = {
            "PRODUCT_TABLE": products_table.table_name,
            "PRODUCT_IMAGE_BUCKET": image_bucket.bucket_name
        }

        # Package Pydantic into a Lambda Layer
        pydantic_layer = aws_lambda.LayerVersion(
            self, "PydanticLayer",
            code=aws_lambda.Code.from_asset("layers/pydantic"),
            compatible_runtimes=[lambda_runtime],
            description="Layer containing Pydantic"
        )

        # Create Dead-Letter Queue
        self.dlq = sqs.Queue(
            self, "ProductApiDLQ",
            queue_name="product-api-dlq",
            retention_period=Duration.days(14),
            visibility_timeout=Duration.minutes(5)
        )

        # Core Lambda functions
        self.get_product = aws_lambda.Function(
            self, "GetProduct",
            runtime=lambda_runtime,
            handler="lambda_code.get_product.handler",
            code=code_location,
            environment=common_env
        )
        products_table.grant_read_data(self.get_product)

        self.query_products = aws_lambda.Function(
            self, "QueryProducts",
            runtime=lambda_runtime,
            handler="lambda_code.query_products.handler",
            code=code_location,
            environment=common_env
        )
        products_table.grant_read_data(self.query_products)

        self.insert_product = aws_lambda.Function(
            self, "InsertProduct",
            runtime=lambda_runtime,
            handler="lambda_code.insert_product.handler",
            code=code_location,
            layers=[pydantic_layer],
            dead_letter_queue=self.dlq,
            environment=common_env
        )
        products_table.grant_read_write_data(self.insert_product)

        self.update_product = aws_lambda.Function(
            self, "UpdateProduct",
            runtime=lambda_runtime,
            handler="lambda_code.update_product.handler",
            code=code_location,
            layers=[pydantic_layer],
            environment=common_env
        )
        products_table.grant_read_write_data(self.update_product)

        self.options = aws_lambda.Function(
            self, "Options",
            runtime=lambda_runtime,
            handler="lambda_code.options.handler",
            code=code_location
        )

        # --- Module 06 Image Storage & Event Processing Functions ---

        # 3. Presigned Upload URL Generator
        self.generate_presigned_url = aws_lambda.Function(
            self, "GeneratePresignedUrl",
            runtime=lambda_runtime,
            handler="lambda_code.generate_presigned_url.handler",
            code=code_location,
            environment=common_env
        )
        image_bucket.grant_put(self.generate_presigned_url)

        # 4. Presigned Download URL Generator
        self.generate_download_url = aws_lambda.Function(
            self, "GenerateDownloadUrl",
            runtime=lambda_runtime,
            handler="lambda_code.generate_download_url.handler",
            code=code_location,
            environment=common_env
        )
        image_bucket.grant_read(self.generate_download_url)

        # 5. Update Product Images in DynamoDB
        self.update_product_images = aws_lambda.Function(
            self, "UpdateProductImages",
            runtime=lambda_runtime,
            handler="lambda_code.update_product_images.handler",
            code=code_location,
            environment=common_env
        )
        products_table.grant_read_write_data(self.update_product_images)

        # 6. S3 Event-Driven Image Metadata Processor
        self.process_image_upload = aws_lambda.Function(
            self, "ProcessImageUpload",
            runtime=lambda_runtime,
            handler="lambda_code.process_image_upload.handler",
            code=code_location,
            environment=common_env
        )
        image_bucket.grant_read(self.process_image_upload)
        products_table.grant_read_write_data(self.process_image_upload)

        # Wire S3 Event Notification to trigger ProcessImageUpload
        image_bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.process_image_upload),
            s3.NotificationKeyFilter(prefix="products/", suffix=".jpg")
        )

        # API Gateway setup
        api = apigw.RestApi(
            self, "ProductsAPI",
            deploy_options=apigw.StageOptions(stage_name="dev")
        )

        products = api.root.add_resource("products")
        products.add_method("GET", apigw.LambdaIntegration(self.query_products))
        products.add_method("POST", apigw.LambdaIntegration(self.insert_product))
        products.add_method("OPTIONS", apigw.LambdaIntegration(self.options))

        product_by_id = products.add_resource("{id}")
        product_by_id.add_method("GET", apigw.LambdaIntegration(self.get_product))
        product_by_id.add_method("PUT", apigw.LambdaIntegration(self.update_product))
        product_by_id.add_method("OPTIONS", apigw.LambdaIntegration(self.options))

        # Module 06 Image Endpoints
        upload_url = product_by_id.add_resource("image-upload-url")
        upload_url.add_method("GET", apigw.LambdaIntegration(self.generate_presigned_url))
        upload_url.add_method("OPTIONS", apigw.LambdaIntegration(self.options))

        download_url = product_by_id.add_resource("image-download-url")
        download_url.add_method("GET", apigw.LambdaIntegration(self.generate_download_url))
        download_url.add_method("OPTIONS", apigw.LambdaIntegration(self.options))

        images = product_by_id.add_resource("images")
        images.add_method("POST", apigw.LambdaIntegration(self.update_product_images))
        images.add_method("OPTIONS", apigw.LambdaIntegration(self.options))

        # Print API endpoint and Bucket name after deployment
        CfnOutput(self, "ProductsApiUrl", value=api.url)
        CfnOutput(self, "ProductImageBucketName", value=image_bucket.bucket_name)
