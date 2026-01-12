"""Setup configuration for OpsPilot."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="opspilot",
    version="0.1.0",
    author="Kiran Vijaykumar Choudhari",
    author_email="choudharikiranv2003@gmail.com",
    description="AI-powered production incident analysis tool using multi-agent systems",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/choudharikiranv15/opspilot",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "Topic :: Software Development :: Debuggers",
        "Topic :: System :: Monitoring",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "typer>=0.9.0",
        "rich>=13.0.0",
        "requests>=2.28.0",
        "python-dotenv>=1.0.0",  # For .env file support
    ],
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=4.0.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
        ],
        "redis": [
            "redis>=4.5.0",  # Redis client for incident memory
        ],
        "aws": [
            "boto3>=1.26.0",  # AWS S3 and CloudWatch integration
        ],
        "k8s": [
            "kubernetes>=25.0.0",  # Kubernetes log fetching
        ],
        "all": [
            "redis>=4.5.0",
            "boto3>=1.26.0",
            "kubernetes>=25.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "opspilot=opspilot.cli:app",
        ],
    },
    keywords="ai mlops devops incident-analysis sre production-monitoring agentic-ai",
    project_urls={
        "Bug Reports": "https://github.com/choudharikiranv15/opspilot/issues",
        "Source": "https://github.com/choudharikiranv15/opspilot",
        "Documentation": "https://github.com/choudharikiranv15/opspilot#readme",
    },
)
