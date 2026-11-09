# AWS naming conventions

## Global service considerations
- Amazon S3 bucket names must be globally unique across all AWS accounts
- Amazon CloudFront distribution names are globally scoped
- Amazon Route 53 hosted zone names follow DNS standards
## Regional and partition considerations
- Most AWS resources are region-specific and can share names across regions
- Some services have partition-level uniqueness requirements
- Consider multi-region deployments when establishing naming patterns
## Recommended naming pattern
`<organization>-<application>-<environment>-<component>-<random-suffix>`

Examples :
```sh
acme-ecommerce-prod-api-a1b2c3d4
acme-ecommerce-dev-database-x9y8z7w6
acme-ecommerce-staging-storage-m5n4p3q2
```
## Use memorable names for:

- High-level organizational resources (root S3 buckets for logging)
- Resources that humans frequently reference
- Resources with long lifecycles and stable purposes
## Use generated names for:

- Application-specific resources managed by Infrastructure as Code
- Resources that scale horizontally
- Temporary or ephemeral resources
- Resources in shared development environments

## Namespace isolation
If there are multiple developers working together on a project, consider isolating your namespaces.

- Include developer initials or unique identifiers in resource names
- Use separate AWS accounts for different environments when possible
- Implement resource tagging for ownership and lifecycle management

Example developer namespacing:
```sh
# Individual developer environments
ecommerce-dev-jsmith-api-lambda
ecommerce-dev-mjones-database-rds-instance

# Shared environments
ecommerce-staging-shared-api-lambda
ecommerce-prod-shared-database-rds
```
