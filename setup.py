from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="impact_os_ai",
    version="0.0.1",
    description="ImpactOS AI — MIS Blueprint Platform powered by MAP Framework",
    author="EdZola Technologies",
    author_email="hello@edzola.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
