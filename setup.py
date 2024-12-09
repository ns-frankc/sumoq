from setuptools import setup
import os


def read_requirements(filename):
    try:
        with open(filename) as f:
            return [line.rstrip() for line in f]
    except OSError:
        raise OSError(os.getcwd())


setup(
    name="sumo query builder prompt",
    version="0.1.0",
    description="An interactive sumo query builder",
    author="Chen Chao Shih",
    author_email="frankc@netskope.com",
    license="MIT",
    packages=["sumoq"],
    entry_points="""
        [console_scripts]
        sumoq=sumoq.cli:cli
    """,
    install_requires=read_requirements("requirements.txt"),
    classifiers=[],
)
