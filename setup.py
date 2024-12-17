from setuptools import setup
import os


def read_requirements(filename):
    try:
        with open(filename) as f:
            return [line.rstrip() for line in f]
    except OSError:
        raise OSError(os.getcwd())


setup(
    name="sumoq",
    version="0.1.0",
    description="An interactive sumo query builder",
    author="Chen Chao Shih",
    author_email="frankc@netskope.com",
    license="MIT",
    packages=["sumoq"],
    package_data={"sumoq": ["default-config.yml", "db.json"]},
    entry_points="""
        [console_scripts]
        sumoq=sumoq.cli:cli
    """,
    install_requires=read_requirements("requirements.txt"),
    classifiers=[
        "Topic :: Terminals",
        "Topic :: Text Processing",
        "Programming Language :: Python 3.12",
        "Programming Language :: Python 3.13",
        "License :: MIT License",
        "Intended Audience :: Developers",
        "Environment :: Console",
    ],
)
