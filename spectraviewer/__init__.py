import os
import tornado.ioloop
from . import app
from tornado.options import define, options, parse_command_line

define('port', default='7000')
define('filesystem_path', default=os.environ.get('FILESYSTEM',
                                                 '/home/radiokoza/Plocha/spectra'))  # todo change
define('jobs_path', default=os.environ.get('JOBS',
                                           '/home/radiokoza/Stažené'))  # todo change
define('legend_hide_threshold', default='10')

def main():
    parse_command_line()
    app.Application().listen(int(options.port))
    print('Server is listening on port {}'.format(options.port))
    # initiate tornado loop
    tornado.ioloop.IOLoop.current().start()
