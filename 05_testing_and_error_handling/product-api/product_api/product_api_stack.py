from aws_cdk import aws_dynamodb
from aws_cdk import CfnOutput, Stack, aws_lambda, aws_apigateway as apigw

class ProductApiStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # DynamoDB table for the product catalog
        products_table = aws_dynamodb.Table(self, "ProductsTable",
        table_name="Products",
        partition_key=aws_dynamodb.Attribute(name="id", type=aws_dynamodb.AttributeType.STRING),
        billing_mode=aws_dynamodb.BillingMode.PAY_PER_REQUEST
        )

        # Secondary index for the category queries in products_db.py
        products_table.add_global_secondary_index(
        index_name="category-index",
        partition_key=aws_dynamodb.Attribute(name="category", type=aws_dynamodb.AttributeType.STRING)
        )

        # Define Lambda configuration
        lambda_runtime = aws_lambda.Runtime.PYTHON_3_13
        code_location = aws_lambda.Code.from_asset(
        ".",
        exclude=[".venv", "venv", "cdk.out", ".git", "tests", "__pycache__"]
        )

        # Package Pydantic into a Lambda Layer
        pydantic_layer = aws_lambda.LayerVersion(
            self, "PydanticLayer",
            code=aws_lambda.Code.from_asset("layers/pydantic"),
            compatible_runtimes=[lambda_runtime],
            description="Layer containing Pydantic"
        )

        # Create Lambda functions pointing to your handler code
        self.get_product = aws_lambda.Function(
            self, "GetProduct",
            runtime=lambda_runtime,
            handler="lambda_code.get_product.handler",
            code=code_location
        )
        products_table.grant_read_data(self.get_product)

        self.query_products = aws_lambda.Function(
            self, "QueryProducts",
            runtime=lambda_runtime,
            handler="lambda_code.query_products.handler",
            code=code_location
        )
        products_table.grant_read_data(self.query_products)

        self.insert_product = aws_lambda.Function(
            self, "InsertProduct",
            runtime=lambda_runtime,
            handler="lambda_code.insert_product.handler",
            code=code_location,
            layers=[pydantic_layer]
        )
        products_table.grant_read_write_data(self.insert_product)

        self.update_product = aws_lambda.Function(
            self, "UpdateProduct",
            runtime=lambda_runtime,
            handler="lambda_code.update_product.handler",
            code=code_location,
            layers=[pydantic_layer]
        )
        products_table.grant_read_write_data(self.update_product)

        self.options = aws_lambda.Function(
            self, "Options",
            runtime=lambda_runtime,
            handler="lambda_code.options.handler",
            code=code_location
        )

        # Create API Gateway and wire it to Lambda
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

        # Print the API endpoint after deployment
        CfnOutput(self, "ProductsApiUrl", value=api.url)