import os
import io
import tornado.web
import tornado.websocket
from tornado.options import options
from tornado.ioloop import PeriodicCallback
from matplotlib.backends.backend_webagg_core import \
    FigureManagerWebAgg, NavigationToolbar2WebAgg, \
    new_figure_manager_given_figure
from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib._pylab_helpers import Gcf
import json
from . import spectra_plotter
import traceback

# disable back and forward buttons
NavigationToolbar2WebAgg.toolitems = list(filter(lambda x: x[0] not in ('Back', 'Forward'),
                                                 NavigationToolbar2WebAgg.toolitems))


class BaseHandler(tornado.web.RequestHandler):
    def __init__(self, application, request, **kwargs):
        super(BaseHandler, self).__init__(application, request)

    def write_error(self, status_code, **kwargs):
        self.render('error.html', status_code=status_code, error_message=self._reason)


class MplJsHandler(BaseHandler):
    def get(self):
        self.set_header('Content-Type', 'application/javascript')
        js = FigureManagerWebAgg.get_javascript()
        self.write(js)


class IndexHandler(BaseHandler):
    def get(self):
        self.render('index.html')


class IndexRedirectHandler(tornado.web.RequestHandler):
    def get(self):
        self.redirect(self.reverse_url('index'))


class SpectraViewHandler(BaseHandler):
    async def get(self):
        location = self.get_argument('location', 'filesystem')
        spectra_arg = self.get_argument('spectra', None)
        prefix_arg = self.get_argument('prefix', '.')  # optional parameter
        if not spectra_arg:
            raise tornado.web.HTTPError(400, reason='Missing "spectra" query parameter')
        # expand spectra list
        spectra_list = spectra_arg.split(',')
        spectra_list = list(filter(lambda x: len(x) > 0, map(lambda x: x.strip(), spectra_list)))
        if len(spectra_list) == 0:
            raise tornado.web.HTTPError(400, reason='No spectrum selected')
        # check for location
        if location not in ['filesystem', 'jobs']:
            raise tornado.web.HTTPError(400, reason='Unknown location: "{}"'.format(location))
        fig = Figure()
        axes = fig.add_subplot(111)
        axes.spectra_count = 0
        try:
            spectra_plotter.plot_spectra(axes, spectra_list, location, prefix_arg)
        except Exception as ex:
            traceback.print_exc()
            raise tornado.web.HTTPError(400, reason=str(ex))
        if axes.spectra_count <= int(options.legend_hide_threshold):
            axes.legend()
        fig_num = id(fig)
        manager = new_figure_manager_given_figure(fig_num, fig)
        manager._cidgcf = None  # temporal fix for the current version callbacks
        Gcf.set_active(manager)
        self.render('figure.html', host=self.request.host, fig_num=fig_num)


class PngSpectrumPlotHandler(BaseHandler):
    async def get(self):
        location = self.get_argument('location', 'filesystem')
        spectrum_arg = self.get_argument('spectrum', None)
        if not spectrum_arg:
            raise tornado.web.HTTPError(400, reason="Missing spectrum parameter")
        if location not in ['filesystem', 'jobs']:
            raise tornado.web.HTTPError(400, reason="Unknown location: \"{}\"".format(location))
        self.set_header('Content-Type', 'image/png')
        fig = Figure()
        canvas = FigureCanvas(fig)
        axes = fig.add_subplot(111)
        try:
            spectra_plotter.plot_spectra(axes, [spectrum_arg], location)
        except Exception as ex:
            traceback.print_exc()
            raise tornado.web.HTTPError(400, reason=str(ex))
        axes.set_title(spectrum_arg.split('/')[-1])
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        buf.seek(0)
        self.write(buf.getvalue())
        buf.close()


class WebSocketHandler(tornado.websocket.WebSocketHandler):
    def open(self, fig_num):
        self.supports_binary = True
        self.fig_num = int(fig_num)
        self.manager = Gcf.get_fig_manager(int(fig_num))
        self.manager.add_web_socket(self)
        if hasattr(self, 'set_nodelay'):
            self.set_nodelay(True)
        self.ping_callback = PeriodicCallback(self.send_ping, 10000)
        self.ping_callback.start()
        self.manager.toolbar.zoom()

    def send_ping(self):
        self.ping(b"ping")

    def on_close(self):
        print('Clearing {}'.format(self.fig_num))
        self.ping_callback.stop()
        self.manager.remove_web_socket(self)
        Gcf.destroy(self.fig_num)
        del self.manager
        # import gc
        # gc.collect()

    def on_message(self, message):
        message = json.loads(message)
        if message['type'] == 'supports_binary':
            self.supports_binary = message['value']
        else:
            self.manager.handle_json(message)

    def send_json(self, content):
        self.write_message(json.dumps(content))

    def send_binary(self, blob):
        if self.supports_binary:
            self.write_message(blob, binary=True)
        else:
            data = 'data:image/png;base64,{}'.format(
                blob.encode('base64').replace('\n', '')
            )
            self.write_message(data)


class DownloadHandler(BaseHandler):
    def get(self, fmt, fig_num):
        manager = Gcf.get_fig_manager(int(fig_num))

        mimetypes = {
            'ps': 'application/postscript',
            'eps': 'application/postscript',
            'pdf': 'application/pdf',
            'svg': 'image/svg+xml',
            'png': 'image/png',
            'jpeg': 'image/jpeg',
            'tif': 'image/tiff',
            'emf': 'application/emf'
        }

        self.set_header('Content-Type', mimetypes.get(fmt, 'binary'))

        buff = io.BytesIO()
        manager.canvas.print_figure(buff, format=fmt)
        self.write(buff.getvalue())


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            tornado.web.URLSpec(r'/', IndexRedirectHandler),
            tornado.web.URLSpec(r'/viewer', IndexRedirectHandler),
            tornado.web.URLSpec(r'/viewer/', IndexHandler, name='index'),
            tornado.web.URLSpec(r'/viewer/mpl.js', MplJsHandler, name='mpl'),
            tornado.web.URLSpec(r'/viewer/view', SpectraViewHandler, name='spectra'),
            tornado.web.URLSpec(r'/viewer/([0-9]+)/ws', WebSocketHandler, name='ws'),
            tornado.web.URLSpec(r'/viewer/download.([a-z0-9.]+)/([0-9]+)', DownloadHandler, name='download'),
            tornado.web.URLSpec(r'/api/png', PngSpectrumPlotHandler, name='png-plotter'),
        ]
        settings = {
            'template_path': os.path.join(os.path.dirname(__file__), 'templates'),
            'static_path': os.path.join(os.path.dirname(__file__), 'static'),
            'debug': False
            # xsrf_cookies=True,
        }
        super(Application, self).__init__(handlers, **settings)
