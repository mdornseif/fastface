import sys
from setuptools import setup
from fastface import __version__

__author__ = {
    "name" : "Ömer BORHAN",
    "email": "borhano.f.42@gmail.com"
}

# load long description
with open("README.md", "r") as foo:
    long_description = foo.read()

# load requirements
with open("requirements.txt", "r") as foo:
    requirements = foo.read().split("\n")

setup(
    # package name `pip install fastface`
    name="fastface",
    # package version `major.minor.patch`
    version=__version__,
    # small description
    description="A face detection framework for edge devices using pytorch lightning",
    # long description
    long_description=long_description,
    # content type of long description
    long_description_content_type="text/markdown",
    # source code url for this package
    url="https://github.com/borhanMorphy/light-face-detection",
    # author of the repository
    author=__author__["name"],
    # author's email adress
    author_email=__author__["email"],
    # package license
    license='MIT',
    # package root directory
    packages=["fastface"],

    install_requires=requirements,
    include_package_data=True,
    # keywords that resemble this package
    keywords=["pytorch_lightning", "face detection", "edge AI", "LFFD"],
    zip_safe=False,
    # classifiers for the package
    classifiers=[
        'Environment :: Console',
        'Natural Language :: English',
        'Intended Audience :: Developers',
        'Intended Audience :: Researchers',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Topic :: Scientific/Engineering :: Object Detection',
        'Topic :: Scientific/Engineering :: Face Detection',

        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.7'
    ]
)