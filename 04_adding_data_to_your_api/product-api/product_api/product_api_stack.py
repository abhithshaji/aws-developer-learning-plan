from aws_cdk import CfnOutput, Stack, aws_lambda, aws_apigateway as apigw

class ProductApiStack(Stack):
    def __init__(self, scope, construct_id, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Create Lambda functions pointing to your handler code
        self.get_product = aws_lambda.Function(
            self, "GetProduct",
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            handler="get_product.handler",
            code=aws_lambda.Code.from_asset("lambda_code")
        )

        self.query_products = aws_lambda.Function(
            self, "QueryProducts",
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            handler="query_products.handler",
            code=aws_lambda.Code.from_asset("lambda_code")
        )

        self.insert_product = aws_lambda.Function(
            self, "InsertProduct",
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            handler="insert_product.handler",
            code=aws_lambda.Code.from_asset("lambda_code")
        )

        self.update_product = aws_lambda.Function(
            self, "UpdateProduct",
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            handler="update_product.handler",
            code=aws_lambda.Code.from_asset("lambda_code")
        )

        self.options = aws_lambda.Function(
            self, "Options",
            runtime=aws_lambda.Runtime.PYTHON_3_13,
            handler="options.handler",
            code=aws_lambda.Code.from_asset("lambda_code")
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