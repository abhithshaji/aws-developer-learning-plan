# ☁️ AWS Developer Learning Plan — Hands-On Companion Guide

[![AWS](https://img.shields.io/badge/AWS-Cloud-orange?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/)
[![AWS CDK](https://img.shields.io/badge/CDK-v2-red?logo=amazon-aws&logoColor=white)](https://aws.amazon.com/cdk/)
[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python&logoColor=white)](https://www.python.org/)
[![Status](https://img.shields.io/badge/Status-In%20Progress-brightgreen)](#-repository-roadmap--structure)
[![Learning Plan](https://img.shields.io/badge/AWS%20Skill%20Builder-Developer%20Learning%20Plan-yellow)](https://explore.skillbuilder.aws/)

A structured, module-by-module code companion and reference guide for developers progressing through the **AWS Developer Learning Plan** on **AWS Skill Builder**.

---

## 📌 Table of Contents

- [About This Repository](#-about-this-repository)
- [Why This Repository Exists](#-why-this-repository-exists)
- [How to Use This Repository](#-how-to-use-this-repository)
- [Repository Roadmap & Structure](#-repository-roadmap--structure)
- [Prerequisites & Environment Setup](#-prerequisites--environment-setup)
- [Official Resources & References](#-official-resources--references)
- [Disclaimer](#-disclaimer)

---

## 📖 About This Repository

The **AWS Developer Learning Plan** on [AWS Skill Builder](https://explore.skillbuilder.aws/) guides developers through building an end-to-end, production-grade cloud application (a Product Catalog API and e-commerce backend) using **AWS CDK (Python)**, **Amazon API Gateway**, **AWS Lambda**, **Amazon DynamoDB**, **Amazon S3**, and event-driven services.

This repository serves as a **practical, incremental companion** containing verified working code, clear directory structures, and configuration files for each course module as you advance through the curriculum.

---

## 🎯 Why This Repository Exists

While working through the AWS Skill Builder curriculum, learners often encounter a few common roadblocks:

1. **Incremental Transitions & Missing Context**  
   Modules build directly upon the codebase of previous modules. However, transitioning between lessons can be challenging when it's unclear **where** new files belong or **which specific files and lines** need modification in existing stacks.
   
2. **Fragmented Code Snippets**  
   Skill Builder provides snippets of code within its lesson text, but frequently omits guidance on overall directory layout, imports, and file organization.

3. **Gaps in the Official AWS Sample Repository**  
   The official [aws-samples/sample-aws-developer-project](https://github.com/aws-samples/sample-aws-developer-project) repository provides only **initial** and **final** states of the project. Furthermore, some code snippets in the official repo diverge slightly from what is presented in the Skill Builder course modules.

### The Solution

This repository provides **isolated, working code snapshots for each module**:
- ✅ **Full Directory Visibility:** See exact folder layouts and where each file lives.
- ✅ **Clean Module Separation:** Inspect working states at each milestone without having to jump straight to the final project code.
- ✅ **Troubleshooting Baseline:** Quickly compare your code when facing deployment or runtime issues.

---

## 🚀 How to Use This Repository

To maximize your learning experience, we recommend following this workflow:

```text
    [1. Learn on AWS Skill Builder] --> [2. Build & Code Locally]
    Does it deploy & work?
        Yes --> [3. Proceed to Next Module]
        Stuck / Errors --> [4. Consult This Repo's Module Folder]
    [5. Check Directory Layout & File Differences]
```

1. **Follow the Skill Builder Course First**: Go through the theory and instructions on AWS Skill Builder and write and deploy the code in your own AWS development environment.
2. **Use as a Reference, Not a Shortcut**: When you get stuck, encounter syntax or import errors, or wonder how to organize files, open the corresponding module directory here (e.g., `03_building_your_first_serverless_api/`).
3. **Compare File Structures**: Verify your directory layout against the module's structure, paying close attention to CDK stack definitions (`product_api/`) and Lambda function code (`lambda_code/`).
4. **Cross-Check with Official Sample Code**: Use the [official AWS repo](https://github.com/aws-samples/sample-aws-developer-project) as an additional reference for overarching architectural patterns and final states.

---

## 📂 Repository Roadmap & Structure

Each folder represents an individual milestone in the learning plan:

```text
aws-developer-learning-plan/
├── 01_introduction_to_aws_developer_learning_plan/   # Environment setup, CLI verification & resource provisioning
├── 02_introduction_to_being_an_aws_developer/        # AWS naming conventions, partition considerations & namespacing
├── 03_building_your_first_serverless_api/            # CDK project init, virtual env setup & basic API stack
└── README.md                                         # Main documentation & companion guide
```

### Module Breakdown

| Module | Topic / Focus | Key Concepts & AWS Services | Status |
|---|---|---|:---:|
| **01** | [Introduction & Setup](./01_introduction_to_aws_developer_learning_plan) | CLI verification, DynamoDB provisioning, S3 bucket creation, data seeding | ✅ Complete |
| **02** | [AWS Developer Fundamentals](./02_introduction_to_being_an_aws_developer) | Resource naming strategies, global vs regional scope, namespace isolation | ✅ Complete |
| **03** | [First Serverless API](./03_building_your_first_serverless_api) | AWS CDK (Python), API Gateway, Lambda, virtual environments | 🔄 In Progress |
| **04+** | *Upcoming Modules* | Data access, SQS/SNS messaging, Cognito authentication, CI/CD, Observability | ⏳ Planned |

---

## 🛠️ Prerequisites & Environment Setup

Before working on the modules, make sure your local environment is configured:

1. **AWS Account**: An active AWS account with administrative or developer-level IAM privileges.
2. **AWS CLI (v2)**: Installed and configured with your credentials:
   ```bash
   aws sts get-caller-identity
   ```
3. **AWS CDK CLI**: Installed globally via Node.js:
   ```bash
   npm install -g aws-cdk
   cdk --version
   ```
4. **Python 3.9+ & Virtual Environments**:
   ```bash
   python3 --version
   pip --version
   ```

> [!NOTE]
> All resources provisioned in the initial modules (such as on-demand DynamoDB tables and S3 buckets) are configured to use pay-per-request pricing so they incur minimal or zero cost when idle. Remember to clean up unused resources when you conclude your practice sessions.

---

## 🔗 Official Resources & References

- 🎓 **[AWS Skill Builder](https://skillbuilder.aws/)** — Home of the AWS Developer Learning Plan.
- 📦 **[Official AWS Project Repository (`aws-samples`)](https://github.com/aws-samples/sample-aws-developer-project)** — The official sample repository containing initial and final project states.
- 📚 **[AWS CDK Documentation](https://docs.aws.amazon.com/cdk/v2/guide/home.html)** — Comprehensive guide to AWS Cloud Development Kit.
- 📖 **[AWS CLI Command Reference](https://awscli.amazonaws.com/v2/documentation/api/latest/index.html)** — Reference for all AWS CLI commands.

---

## 📄 Disclaimer

This repository is an independent, community-driven educational companion created to aid learning and troubleshooting during the AWS Developer Learning Plan. It is not officially affiliated with, endorsed by, or maintained by Amazon Web Services (AWS). All AWS product names, logos, and brands are property of their respective owners.
