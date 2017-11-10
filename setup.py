from setuptools import setup

setup(name='jupyter_micropython_kernel',
      version='0.1.3',
      description='Jupyter notebook kernel for operating Micropython.',
      author='Julian Todd, Tony DiCola',
      author_email='julian@goatchurch.org.uk',
      keywords='jupyter micropython',
      url='https://github.com/goatchurchprime/jupyter_micropython_kernel',
      license='GPL3',
      packages=['jupyter_micropython_kernel'],
      install_requires=['pyserial>=3.4', 'websocket-client>=0.44']
)

