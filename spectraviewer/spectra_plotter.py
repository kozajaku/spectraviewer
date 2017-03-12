from tornado.options import options
import os
from astropy.io import fits, votable
import warnings
import csv
import re


class UnknownExtensionException(Exception):
    pass


class AbstractPlotter:
    """Abstract definition of plooter. Uses parsing ability of subclasses to obtain spectrum name,
    and its x and y axes (wave and flux)."""

    def plot(self, axes, file_name, file_path, **kwargs):
        parsed_fits = self._parse_spectrum_file(file_path)
        name = file_name
        if parsed_fits['name']:
            name = '{}: {}'.format(name, parsed_fits['name'])
        axes.plot(parsed_fits['wave'], parsed_fits['flux'], label=name)
        axes.spectra_count += 1


class VotPlotter(AbstractPlotter):
    """Plotter class capable of plotting .vot spectrum files (either binary or text column based)"""

    def _parse_spectrum_file(self, file):
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            vot = votable.parse(file)
        table = vot.get_first_table()
        data = table.array
        wave = data['spectral']
        flux = data['flux']
        try:
            name = table.get_field_by_id_or_name('ssa_targname').value
            if type(name) is bytes:
                name = name.decode()
        except AttributeError:
            name = None
        return {
            'name': name,
            'wave': wave,
            'flux': flux
        }


class FitsPlotter(AbstractPlotter):
    """Plotter class capable of plotting .fits spectrum files."""

    def _parse_spectrum_file(self, file):
        with fits.open(file) as hdulist:
            for hdu in hdulist:
                if hdu.data is None:
                    continue
                # obtain name
                name = hdu.header.get('object')
                naxis = hdu.header.get('naxis')
                if naxis == 2:
                    # tabledata
                    tbdata = hdu.data
                    wave = tbdata.field(0).tolist()
                    flux = tbdata.field(1).tolist()
                elif naxis == 1:
                    flux = hdu.data.tolist()
                    # wave must be mapped manually
                    length = len(flux)
                    start = hdu.header['crval1']
                    delta = hdu.header['cdelt1']
                    wave = [start + i * delta for i in range(length)]
        return {
            'name': name,
            'wave': wave,
            'flux': flux
        }


class CsvPlotter:
    """Plotter class capable of plotting multiple spectra from the single csv file."""

    def plot(self, axes, file_name, file_path, meta_file=None, **kwargs):
        # parse wave from meta file if any
        wave = None
        if meta_file:
            raise NotImplementedError  # todo
        with open(file_path, newline='') as csvfile:
            line = csvfile.readline()
            csvfile.seek(0)
            # find out delimiter
            if line.count(' ') > line.count(','):
                delimiter = ' '
            else:
                delimiter = ','
            first = line.partition(delimiter)[0]
            if re.match(r'^[a-zA-Z].*$', first):
                names = True
            else:
                names = False
            csv_reader = csv.reader(csvfile, delimiter=delimiter)
            counter = 0
            for spectrum in csv_reader:
                if names:
                    name = spectrum[0]
                    flux = spectrum[1:]
                else:
                    name = '{}: #{}'.format(file_name, counter)
                    counter += 1
                    flux = spectrum
                if wave:
                    axes.plot(wave, flux, label=name)
                else:
                    axes.plot(flux, label=name)
                axes.spectra_count += 1


PLOTTER_MAPPING = {
    'fits': FitsPlotter(),
    'fit': FitsPlotter(),
    'vot': VotPlotter(),
    'csv': CsvPlotter()
}


def file_extension(filename):
    """
    Returns file extension of the passed file_name. If there is no such extension
    returns None.

    :param filename: File name of the file where the extension must be found out from.
    :return: The extension string without '.' character or None if there is no extension.
    """
    if not filename:
        raise ValueError('No filename passed')
    arr = filename.split('.')
    if len(arr) <= 1:
        return None
    ext = arr[-1].strip()
    if len(ext) == 0:
        return None
    return ext


def plot_spectra(axes, file_list, location):
    """
    Plot passed files into specified matplotlib axes.

    :param axes: Matplotlib axes which spectra should be plotted to.
    :param file_list: List of file paths containing spectra. The paths are absolute paths inside the specified location.
    :param location: Spectra location. Currently supported are filesystem and jobs.
    :return: Passed axes where spectra have been plotted to.
    """
    if len(file_list) == 0:
        raise ValueError('Empty file list')
    if location == 'filesystem':
        location_prefix = options.filesystem_path
    elif location == 'jobs':
        location_prefix = options.jobs_path
    else:
        # unsupported option
        raise ValueError('Unsupported location option: {}'.format(location))
    # map files to real locations as (filename, abspath)
    files = map(lambda x: (os.path.basename(x),
                           os.path.abspath(os.path.join(location_prefix, x))), file_list)
    for f in files:
        if not os.path.isfile(f[1]):
            raise ValueError('Spectrum file {} in location {} does not exist'
                             .format(f[0], f[1]))
        # try to find out plotter
        ext = file_extension(f[0])
        plotter = PLOTTER_MAPPING.get(ext)
        if plotter is None:
            raise UnknownExtensionException('Unknown spectrum file extension to plot: {}'
                                            .format(ext))
        # plot spectrum
        plotter.plot(axes, *f)
    return axes
