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
        parsed_spectrum = self._parse_spectrum_file(file_path)
        name = file_name
        if parsed_spectrum['name'] is not None:
            name = '{}: {}'.format(name, parsed_spectrum['name'])
        if parsed_spectrum['wave'] is not None:
            axes.plot(parsed_spectrum['wave'], parsed_spectrum['flux'], label=name)
        else:
            axes.plot(parsed_spectrum['flux'], label=name)
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
        print(wave)
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

    def _extract_wave(self, hdu, flux):
        pix = int(hdu.header['crpix1'])
        first = hdu.header['crval1']
        try:
            delta = hdu.header['cdelt1']
        except KeyError:
            delta = hdu.header['cd1_1']
        try:
            dc_flag = hdu.header['dc-flag']
        except KeyError:
            dc_flag = 0  # implicit linear sampling
        if dc_flag == 0:
            # linear sampling
            wave = [first + (i - pix + 1) * delta for i in range(len(flux))]
        else:
            # logarithmic sampling
            wave = [10 ** (first + (i - pix + 1) * delta) for i in range(len(flux))]
        return wave

    def _parse_spectrum_file(self, file):
        with fits.open(file) as hdulist:
            for hdu in hdulist:
                if hdu.data is None:
                    continue
                # obtain name
                name = hdu.header.get('object', hdu.header.get('desig'))
                naxis = hdu.header.get('naxis')
                if naxis == 2 and hdu.header.get('naxis2') == 5:
                    flux = hdu.data[0]
                    wave = self._extract_wave(hdu, flux)
                elif naxis == 2:
                    # tabledata
                    tbdata = hdu.data
                    try:
                        wave = tbdata['spectral']
                    except KeyError:
                        wave = tbdata['wave']
                    flux = tbdata['flux']
                    # except KeyError:
                    #     # fall back to non-tabledata format
                    #     wave = tbdata[0]
                    #     flux = tbdata[1]
                elif naxis == 1:
                    flux = hdu.data.tolist()
                    wave = self._extract_wave(hdu, flux)

        return {
            'name': name,
            'wave': wave,
            'flux': flux
        }


class CsvPlotter:
    """Plotter class capable of plotting multiple spectra from the single csv file."""

    def plot(self, axes, file_name, file_path, meta_wave=None, **kwargs):
        # parse wave from meta file if any
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
                if meta_wave is not None:
                    axes.plot(meta_wave, flux, label=name)
                else:
                    axes.plot(flux, label=name)
                axes.spectra_count += 1


PLOTTER_MAPPING = {
    'fits': FitsPlotter(),
    'fit': FitsPlotter(),
    'vot': VotPlotter(),
    'csv': CsvPlotter(),
    'xml': VotPlotter()
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


def extract_meta_file(file):
    """
    Attempt to extract wave meta data from meta.xml file. This file should contain wave (x axis)
    of spectra listed in csv files. The meta.xml file has a votable format.

    :param file: Path to existing meta.xml file.
    :return: Extracted list of wave values, None if the meta.xml is invalid.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            vot = votable.parse(file)
        table = vot.get_first_table()
        data = table.array
        wave = data['intensities']
        return wave[0]
    except Exception as ex:
        print('meta.xml reading failed: ', ex)
        return None


def path_mapper(location_prefix):
    def submapper(path):
        while path.startswith('/'):
            path = path[1:]
        if '..' in path:
            raise ValueError('\'..\' path characters are forbidden')
        return (os.path.basename(path),
                os.path.abspath(os.path.join(location_prefix, path)))

    return submapper


def plot_spectra(axes, file_list, location):
    """
    Plot passed files into specified matplotlib axes.

    :param axes: Matplotlib axes which spectra should be plotted to.
    :param file_list: List of file paths containing spectra. The paths are absolute paths inside the specified location.
    :param location: Spectra location. Currently supported are filesystem and jobs.
    :return: Passed axes where spectra have been plotted to.
    """
    if len(file_list) == 0:
        raise ValueError('No supported spectrum file found')
    if location == 'filesystem':
        location_prefix = options.filesystem_path
    elif location == 'jobs':
        location_prefix = options.jobs_path
    else:
        # unsupported option
        raise ValueError('Unsupported location option: {}'.format(location))
    # map files to real locations as (filename, abspath)
    files = map(path_mapper(location_prefix), file_list)
    meta_wave = None
    spectra_files = []
    for f in files:
        if not os.path.isfile(f[1]):
            raise ValueError('Spectrum file {} in location {} does not exist'
                             .format(f[0], f[1]))  # meta file detection
        if f[0] == 'meta.xml':
            meta_wave = extract_meta_file(f[1])
        else:
            spectra_files.append(f)
    if len(spectra_files) == 0:
        raise ValueError('No supported spectrum file found')
    for f in spectra_files:
        # try to find out plotter
        ext = file_extension(f[0])
        plotter = PLOTTER_MAPPING.get(ext)
        if plotter is None:
            raise UnknownExtensionException('Unknown spectrum file extension to plot: {}'
                                            .format(ext))
        # plot spectrum
        plotter.plot(axes, *f, meta_wave=meta_wave)
    return axes
