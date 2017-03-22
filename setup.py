from setuptools import setup, find_packages

with open('README.rst') as f:
    long_description = ''.join(f.readlines())

setup(
    name='spectraviewer',
    version='0.1',
    packages=find_packages(),
    url='https://github.com/kozajaku/spectraviewer',
    license='MIT',
    author='kozajaku',
    author_email='kozajaku@fit.cvut.cz',
    description='HTTP server for interactive spectra viewing',
    long_description=long_description,
    include_package_data=True,
    classifiers=[
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3.5',
    ],
    keywords='spectra,astroinformatics,astronomy',
    install_requires=[
        'tornado>=4.4',
        'matplotlib>=2.0',
        'astropy>=1.3',
    ],
    package_data={
        'spectraviewer': ['static/*', 'templates/*.html']
    },
    entry_points={
        'console_scripts': ['spectraviewer=spectraviewer:main'],
    }
)
