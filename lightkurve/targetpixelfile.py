from __future__ import division
import datetime
import os
import warnings
import logging

from astropy.io import fits
from astropy.nddata import Cutout2D
from astropy.table import Table
from astropy.wcs import WCS
from matplotlib import patches
import matplotlib.pyplot as plt
import numpy as np
from tqdm import tqdm
from astropy.coordinates import SkyCoord
from astropy.wcs.utils import skycoord_to_pixel, pixel_to_skycoord

from . import PACKAGEDIR
from .lightcurve import KeplerLightCurve, LightCurve
from .prf import SimpleKeplerPRF
from .utils import KeplerQualityFlags, plot_image, bkjd_to_astropy_time
from .mast import download_kepler_products



__all__ = ['KeplerTargetPixelFile']
log = logging.getLogger(__name__)


class TargetPixelFile(object):
    """
    Generic TargetPixelFile class
    """

    def properties(self):
        '''Print out a description of each of the non-callable attributes of a
        TargetPixelFile object.

        Prints in order of type (ints, strings, lists, arrays and others)
        Prints in alphabetical order.'''
        attrs = {}
        for attr in dir(self):
            if not attr.startswith('_'):
                res = getattr(self, attr)
                if callable(res):
                    continue
                if attr == 'hdu':
                    attrs[attr] = {'res': res, 'type': 'list'}
                    for idx, r in enumerate(res):
                        if idx == 0:
                            attrs[attr]['print'] = '{}'.format(r.header['EXTNAME'])
                        else:
                            attrs[attr]['print'] = '{}, {}'.format(attrs[attr]['print'],
                                                                   '{}'.format(r.header['EXTNAME']))
                    continue
                else:
                    attrs[attr] = {'res': res}
                if isinstance(res, int):
                    attrs[attr]['print'] = '{}'.format(res)
                    attrs[attr]['type'] = 'int'
                elif isinstance(res, np.ndarray):
                    attrs[attr]['print'] = 'array {}'.format(res.shape)
                    attrs[attr]['type'] = 'array'
                elif isinstance(res, list):
                    attrs[attr]['print'] = 'list length {}'.format(len(res))
                    attrs[attr]['type'] = 'list'
                elif isinstance(res, str):
                    if res == '':
                        attrs[attr]['print'] = '{}'.format('None')
                    else:
                        attrs[attr]['print'] = '{}'.format(res)
                    attrs[attr]['type'] = 'str'
                elif attr == 'wcs':
                    attrs[attr]['print'] = 'astropy.wcs.wcs.WCS'.format(attr)
                    attrs[attr]['type'] = 'other'
                else:
                    attrs[attr]['print'] = '{}'.format(type(res))
                    attrs[attr]['type'] = 'other'
        output = Table(names=['Attribute', 'Description'], dtype=[object, object])
        idx = 0
        types = ['int', 'str', 'list', 'array', 'other']
        for typ in types:
            for attr, dic in attrs.items():
                if dic['type'] == typ:
                    output.add_row([attr, dic['print']])
                    idx += 1
        output.pprint(max_lines=-1, max_width=-1)


class TessTargetPixelFile(TargetPixelFile):
    """
    Defines a TargetPixelFile class for the TESS Mission.
    Enables extraction of raw lightcurves and centroid positions.

    Attributes
    ----------
    path : str
        Path to a Kepler Target Pixel (FITS) File.
    quality_bitmask : str or int
        Bitmask specifying quality flags of cadences that should be ignored.
        If a string is passed, it has the following meaning:

            * "default": recommended quality mask
            * "hard": removes more flags, known to remove good data
            * "hardest": removes all data that has been flagged

    References
    ----------
    .. [1] Kepler: A Search for Terrestrial Planets. Kepler Archive Manual.
        http://archive.stsci.edu/kepler/manuals/archive_manual.pdf
    """
    pass


class KeplerTargetPixelFile(TargetPixelFile):
    """
    Defines a TargetPixelFile class for the Kepler/K2 Mission.
    Enables extraction of raw lightcurves and centroid positions.

    Attributes
    ----------
    path : str or `astropy.io.fits.HDUList`
        Path to a Kepler Target Pixel (FITS) File or a `HDUList` object.
    quality_bitmask : str or int
        Bitmask specifying quality flags of cadences that should be ignored.
        If `None` is passed, then no cadences are ignored.
        If a string is passed, it has the following meaning:

            * "default": recommended quality mask
            * "hard": removes more flags, known to remove good data
            * "hardest": removes all data that has been flagged

        See the `KeplerQualityFlags` class for details on the bitmasks.

    References
    ----------
    .. [1] Kepler: A Search for Terrestrial Planets. Kepler Archive Manual.
        http://archive.stsci.edu/kepler/manuals/archive_manual.pdf
    """

    def __init__(self, path, quality_bitmask='default', **kwargs):
        self.path = path
        if isinstance(path, fits.HDUList):
            self.hdu = path
        else:
            self.hdu = fits.open(self.path, **kwargs)
        self.quality_bitmask = quality_bitmask
        self.quality_mask = self._quality_mask(quality_bitmask)

    @staticmethod
    def from_archive(target, cadence='long', quarter=None, month=None,
                     campaign=None, radius=1., targetlimit=1, **kwargs):
        """Fetch a Target Pixel File from the Kepler/K2 data archive at MAST.

        Raises an `ArchiveError` if a unique TPF cannot be found.  For example,
        this is the case if a target was observed in multiple Quarters and the
        quarter parameter is unspecified.

        Parameters
        ----------
        target : str or int
            KIC/EPIC ID or object name.
        cadence : str
            'long' or 'short'.
        quarter, campaign : int, list of ints, or 'all'
            Kepler Quarter or K2 Campaign number.
        month : 1, 2, 3, list or 'all'
            For Kepler's prime mission, there are three short-cadence
            Target Pixel Files for each quarter, each covering one month.
            Hence, if cadence='short' you need to specify month=1, 2, or 3.
        radius : float
            Search radius in arcseconds. Default is 1 arcsecond.
        targetlimit : None or int
            If multiple targets are present within `radius`, limit the number
            of returned TargetPixelFile objects to `targetlimit`.
            If `None`, no limit is applied.
        kwargs : dict
            Keywords arguments passed to `KeplerTargetPixelFile`.

        Returns
        -------
        tpf : KeplerTargetPixelFile object.
        """
        path = download_kepler_products(
            target=target, filetype='Target Pixel', cadence=cadence,
            quarter=quarter, campaign=campaign, month=month,
            radius=radius, targetlimit=targetlimit)
        if len(path) == 1:
            return KeplerTargetPixelFile(path[0], **kwargs)
        return [KeplerTargetPixelFile(p, **kwargs) for p in path]

    def __repr__(self):
        return('KeplerTargetPixelFile Object (ID: {})'.format(self.keplerid))

    @property
    def hdu(self):
        return self._hdu

    @hdu.setter
    def hdu(self, value, keys=['FLUX', 'QUALITY']):
        '''Raises a ValueError exception if value does not appear to be a Target Pixel File.
        '''
        for key in keys:
            if ~(np.any([value[1].header[ttype] == key
                         for ttype in value[1].header['TTYPE*']])):
                raise ValueError("File {} does not have a {} column, "
                                 "is this a target pixel file?".format(self.path, key))
        else:
            self._hdu = value

    def _quality_mask(self, bitmask):
        """Returns a boolean mask which flags all good-quality cadences.

        Parameters
        ----------
        bitmask : str or int
            Bitmask. See ref. [1], table 2-3.
        """
        if bitmask is None:
            return np.ones(len(self.hdu[1].data['TIME']), dtype=bool)
        elif isinstance(bitmask, str):
            bitmask = KeplerQualityFlags.OPTIONS[bitmask]
        return (self.hdu[1].data['QUALITY'] & bitmask) == 0

    def header(self, ext=0):
        """Returns the header for a given extension."""
        return self.hdu[ext].header

    def get_prf_model(self):
        """Returns an object of SimpleKeplerPRF initialized using the
        necessary metadata in the tpf object.

        Returns
        -------
        prf : instance of SimpleKeplerPRF
        """

        return SimpleKeplerPRF(channel=self.channel, shape=self.shape[1:],
                               column=self.column, row=self.row)

    @property
    def wcs(self):
        """Returns an astropy.wcs.WCS object with the World Coordinate System
        solution for the target pixel file.

        Returns
        -------
        w : astropy.wcs.WCS object
            WCS solution
        """
        # Use WCS keywords of the 5th column (FLUX)
        wcs_keywords = {'1CTYP5': 'CTYPE1',
                        '2CTYP5': 'CTYPE2',
                        '1CRPX5': 'CRPIX1',
                        '2CRPX5': 'CRPIX2',
                        '1CRVL5': 'CRVAL1',
                        '2CRVL5': 'CRVAL2',
                        '1CUNI5': 'CUNIT1',
                        '2CUNI5': 'CUNIT2',
                        '1CDLT5': 'CDELT1',
                        '2CDLT5': 'CDELT2',
                        '11PC5': 'PC1_1',
                        '12PC5': 'PC1_2',
                        '21PC5': 'PC2_1',
                        '22PC5': 'PC2_2'}
        mywcs = {}
        for oldkey, newkey in wcs_keywords.items():
            mywcs[newkey] = self.hdu[1].header[oldkey]
        return WCS(mywcs)

    def get_coordinates(self, cadence='all'):
        """Returns two 3D arrays of RA and Dec values in decimal degrees.

        If cadence number is given, returns 2D arrays for that cadence. If
        cadence is 'all' returns one RA, Dec value for each pixel in every cadence.
        Uses the WCS solution and the POS_CORR data from TPF header.

        Parameters
        ----------
        cadence : 'all' or int
            Which cadences to return the RA Dec coordinates for.

        Returns
        -------
        ra : numpy array, same shape as tpf.flux[cadence]
            Array containing RA values for every pixel, for every cadence.
        dec : numpy array, same shape as tpf.flux[cadence]
            Array containing Dec values for every pixel, for every cadence.
        """
        w = self.wcs
        X, Y = np.meshgrid(np.arange(self.shape[2]), np.arange(self.shape[1]))
        pos_corr1_pix, pos_corr2_pix = np.copy(self.hdu[1].data['POS_CORR1']), np.copy(self.hdu[1].data['POS_CORR2'])

        # We zero POS_CORR* when the values are NaN or make no sense (>50px)
        with warnings.catch_warnings():  # Comparing NaNs to numbers is OK here
            warnings.simplefilter("ignore", RuntimeWarning)
            bad = np.any([~np.isfinite(pos_corr1_pix),
                          ~np.isfinite(pos_corr2_pix),
                          np.abs(pos_corr1_pix - np.nanmedian(pos_corr1_pix)) > 50,
                          np.abs(pos_corr2_pix - np.nanmedian(pos_corr2_pix)) > 50], axis=0)
        pos_corr1_pix[bad], pos_corr2_pix[bad] = 0, 0

        # Add in POSCORRs
        X = (np.atleast_3d(X).transpose([2, 0, 1]) +
             np.atleast_3d(pos_corr1_pix).transpose([1, 2, 0]))
        Y = (np.atleast_3d(Y).transpose([2, 0, 1]) +
             np.atleast_3d(pos_corr2_pix).transpose([1, 2, 0]))

        # Pass through WCS
        ra, dec = w.wcs_pix2world(X.ravel(), Y.ravel(), 1)
        ra = ra.reshape((pos_corr1_pix.shape[0], self.shape[1], self.shape[2]))
        dec = dec.reshape((pos_corr2_pix.shape[0], self.shape[1], self.shape[2]))
        ra, dec = ra[self.quality_mask], dec[self.quality_mask]
        if cadence is not 'all':
            return ra[cadence], dec[cadence]
        return ra, dec

    @property
    def keplerid(self):
        return self.header()['KEPLERID']

    @property
    def obsmode(self):
        return self.header()['OBSMODE']

    @property
    def module(self):
        return self.header()['MODULE']

    @property
    def channel(self):
        return self.header()['CHANNEL']

    @property
    def output(self):
        return self.header()['OUTPUT']

    @property
    def ra(self):
        try:
            return self.header()['RA_OBJ']
        except KeyError:
            return None

    @property
    def dec(self):
        try:
            return self.header()['DEC_OBJ']
        except KeyError:
            return None

    @property
    def column(self):
        try:
            out = self.hdu[1].header['1CRV5P']
        except KeyError:
            out = 0
        return out

    @property
    def row(self):
        try:
            out = self.hdu[1].header['2CRV5P']
        except KeyError:
            out = 0
        return out

    @property
    def pos_corr1(self):
        """Returns the column position correction."""
        return self.hdu[1].data['POS_CORR1'][self.quality_mask]

    @property
    def pos_corr2(self):
        """Returns the row position correction."""
        return self.hdu[1].data['POS_CORR2'][self.quality_mask]

    @property
    def pipeline_mask(self):
        """Returns the aperture mask used by the Kepler pipeline"""
        return self.hdu[-1].data > 2

    @property
    def shape(self):
        """Return the cube dimension shape."""
        return self.flux.shape

    @property
    def time(self):
        """Returns the time for all good-quality cadences."""
        return self.hdu[1].data['TIME'][self.quality_mask]

    @property
    def astropy_time(self):
        """Returns an AstroPy Time object for all good-quality cadences."""
        return bkjd_to_astropy_time(bkjd=self.time)

    @property
    def cadenceno(self):
        """Return the cadence number for all good-quality cadences."""
        return self.hdu[1].data['CADENCENO'][self.quality_mask]

    @property
    def nan_time_mask(self):
        """Returns a boolean mask flagging cadences whose time is `nan`."""
        return ~np.isfinite(self.time)

    @property
    def flux(self):
        """Returns the flux for all good-quality cadences."""
        return self.hdu[1].data['FLUX'][self.quality_mask]

    @property
    def flux_err(self):
        """Returns the flux uncertainty for all good-quality cadences."""
        return self.hdu[1].data['FLUX_ERR'][self.quality_mask]

    @property
    def flux_bkg(self):
        """Returns the background flux for all good-quality cadences."""
        return self.hdu[1].data['FLUX_BKG'][self.quality_mask]

    @property
    def flux_bkg_err(self):
        return self.hdu[1].data['FLUX_BKG_ERR'][self.quality_mask]

    @property
    def quality(self):
        """Returns the quality flag integer of every good cadence."""
        return self.hdu[1].data['QUALITY'][self.quality_mask]

    @property
    def quarter(self):
        """Quarter number"""
        try:
            return self.header(ext=0)['QUARTER']
        except KeyError:
            return None

    @property
    def campaign(self):
        """Campaign number"""
        try:
            return self.header(ext=0)['CAMPAIGN']
        except KeyError:
            return None

    @property
    def mission(self):
        """Mission name, defaults to None if Not available"""
        try:
            return self.header(ext=0)['MISSION']
        except KeyError:
            return None

    def _parse_aperture_mask(self, aperture_mask):
        """Parse the `aperture_mask` parameter as given by a user.

        The `aperture_mask` parameter is accepted by a number of methods.
        This method ensures that the parameter is always parsed in the same way.

        Parameters
        ----------
        aperture_mask : array-like, 'pipeline', 'all', or None
            A boolean array describing the aperture such that `False` means
            that the pixel will be masked out.
            If None or 'all' are passed, a mask that is `True` everywhere will
            be returned.
            If 'pipeline' is passed, the mask suggested by the Kepler pipeline
            will be returned.

        Returns
        -------
        aperture_mask : ndarray
            2D boolean numpy array containing `True` for selected pixels.
        """
        with warnings.catch_warnings():
            # `aperture_mask` supports both arrays and string values; these yield
            # uninteresting FutureWarnings when compared, so let's ignore that.
            warnings.simplefilter(action='ignore', category=FutureWarning)
            if aperture_mask is None or aperture_mask == 'all':
                aperture_mask = np.ones((self.shape[1], self.shape[2]), dtype=bool)
            elif aperture_mask == 'pipeline':
                aperture_mask = self.pipeline_mask
        self._last_aperture_mask = aperture_mask
        return aperture_mask

    def to_lightcurve(self, aperture_mask='pipeline'):
        """Performs aperture photometry.

        Parameters
        ----------
        aperture_mask : array-like, 'pipeline', or 'all'
            A boolean array describing the aperture such that `False` means
            that the pixel will be masked out.
            If the string 'all' is passed, all pixels will be used.
            The default behaviour is to use the Kepler pipeline mask.

        Returns
        -------
        lc : KeplerLightCurve object
            Array containing the summed flux within the aperture for each
            cadence.
        """
        aperture_mask = self._parse_aperture_mask(aperture_mask)
        if aperture_mask.sum() == 0:
            log.warning('Warning: aperture mask contains zero pixels.')
        centroid_col, centroid_row = self.centroids(aperture_mask)
        keys = {'centroid_col': centroid_col,
                'centroid_row': centroid_row,
                'quality': self.quality,
                'channel': self.channel,
                'campaign': self.campaign,
                'quarter': self.quarter,
                'mission': self.mission,
                'cadenceno': self.cadenceno,
                'ra': self.ra,
                'dec': self.dec}

        return KeplerLightCurve(time=self.time,
                                time_format='bkjd',
                                time_scale='tdb',
                                flux=np.nansum(self.flux[:, aperture_mask], axis=1),
                                flux_err=np.nansum(self.flux_err[:, aperture_mask]**2, axis=1)**0.5,
                                **keys)

    def centroids(self, aperture_mask='pipeline'):
        """Returns centroids based on sample moments.

        Parameters
        ----------
        aperture_mask : array-like, 'pipeline', or 'all'
            A boolean array describing the aperture such that `False` means
            that the pixel will be masked out.
            If the string 'all' is passed, all pixels will be used.
            The default behaviour is to use the Kepler pipeline mask.

        Returns
        -------
        col_centr, row_centr : tuple
            Arrays containing centroids for column and row at each cadence
        """
        aperture_mask = self._parse_aperture_mask(aperture_mask)
        yy, xx = np.indices(self.shape[1:]) + 0.5
        yy = self.row + yy
        xx = self.column + xx
        total_flux = np.nansum(self.flux[:, aperture_mask], axis=1)
        with warnings.catch_warnings():
            # RuntimeWarnings may occur below if total_flux contains zeros
            warnings.simplefilter("ignore", RuntimeWarning)
            col_centr = np.nansum(xx * aperture_mask * self.flux, axis=(1, 2)) / total_flux
            row_centr = np.nansum(yy * aperture_mask * self.flux, axis=(1, 2)) / total_flux

        return col_centr, row_centr

    def plot(self, ax=None, frame=0, cadenceno=None, bkg=False, aperture_mask=None,
             show_colorbar=True, mask_color='pink', style='fast', **kwargs):
        """
        Plot a target pixel file at a given frame (index) or cadence number.

        Parameters
        ----------
        ax : matplotlib.axes._subplots.AxesSubplot
            A matplotlib axes object to plot into. If no axes is provided,
            a new one will be generated.
        frame : int
            Frame number. The default is 0, i.e. the first frame.
        cadenceno : int, optional
            Alternatively, a cadence number can be provided.
            This argument has priority over frame number.
        bkg : bool
            If True, background will be added to the pixel values.
        aperture_mask : ndarray
            Highlight pixels selected by aperture_mask.
        show_colorbar : bool
            Whether or not to show the colorbar
        mask_color : str
            Color to show the aperture mask
        style : str
            matplotlib.pyplot.style.context, default is 'fast'
        kwargs : dict
            Keywords arguments passed to `lightkurve.utils.plot_image`.

        Returns
        -------
        ax : matplotlib.axes._subplots.AxesSubplot
            The matplotlib axes object.
        """
        if (style == "fast") and ("fast" not in plt.style.available):
            style = "default"
        if cadenceno is not None:
            try:
                frame = np.argwhere(cadenceno == self.cadenceno)[0][0]
            except IndexError:
                raise ValueError("cadenceno {} is out of bounds, "
                                 "must be in the range {}-{}.".format(
                                     cadenceno, self.cadenceno[0], self.cadenceno[-1]))
        try:
            if bkg and np.any(np.isfinite(self.flux_bkg[frame])):
                pflux = self.flux[frame] + self.flux_bkg[frame]
            else:
                pflux = self.flux[frame]
        except IndexError:
            raise ValueError("frame {} is out of bounds, must be in the range "
                             "0-{}.".format(frame, self.shape[0]))
        with plt.style.context(style):
            img_title = 'Kepler ID: {}'.format(self.keplerid)
            img_extent = (self.column, self.column + self.shape[2],
                          self.row, self.row + self.shape[1])
            ax = plot_image(pflux, ax=ax, title=img_title, extent=img_extent,
                            show_colorbar=show_colorbar, **kwargs)
            ax.grid(False)
        if aperture_mask is not None:
            aperture_mask = self._parse_aperture_mask(aperture_mask)
            for i in range(self.shape[1]):
                for j in range(self.shape[2]):
                    if aperture_mask[i, j]:
                        ax.add_patch(patches.Rectangle((j+self.column, i+self.row),
                                                       1, 1, color=mask_color, fill=True,
                                                       alpha=.6))
        return ax

    def interact(self, lc=None):
        """Display an interactive IPython Notebook widget to inspect the data.

        The widget will show both the lightcurve and pixel data.  By default,
        the lightcurve shown is obtained by calling the `to_lightcurve()` method,
        unless the user supplies a custom `LightCurve` object.

        Note: at this time, this feature only works inside an active Jupyter
        Notebook, and tends to be too slow when more than ~30,000 cadences
        are contained in the TPF (e.g. short cadence data).

        Parameters
        ----------
        lc : LightCurve object
            An optional pre-processed lightcurve object to show.
        """
        try:
            from ipywidgets import interact
            import ipywidgets as widgets
            from bokeh.io import push_notebook, show, output_notebook
            from bokeh.plotting import figure, ColumnDataSource
            from bokeh.models import Span, LogColorMapper
            from bokeh.layouts import row
            from bokeh.models.tools import HoverTool
            from IPython.display import display
            output_notebook()
        except ImportError:
            raise ImportError('The quicklook tool requires Bokeh and ipywidgets. '
                              'See the .interact() tutorial')

        ytitle = 'Flux'
        if lc is None:
            lc = self.to_lightcurve()
            ytitle = 'Flux (e/s)'

        # Bokeh cannot handle many data points
        # https://github.com/bokeh/bokeh/issues/7490
        if len(lc.cadenceno) > 30000:
            raise RuntimeError('Interact cannot display more than 20000 cadences.')

        # Map cadence to index for quick array slicing.
        n_lc_cad = len(lc.cadenceno)
        n_cad, nx, ny = self.flux.shape
        lc_cad_matches = np.in1d(self.cadenceno, lc.cadenceno)
        if lc_cad_matches.sum() != n_lc_cad:
            raise ValueError("The lightcurve provided has cadences that are not "
                             "present in the Target Pixel File.")
        min_cadence, max_cadence = np.min(self.cadenceno), np.max(self.cadenceno)
        cadence_lookup = {cad: j for j, cad in enumerate(self.cadenceno)}
        cadence_full_range = np.arange(min_cadence, max_cadence, 1, dtype=np.int)
        missing_cadences = list(set(cadence_full_range)-set(self.cadenceno))

        # Convert binary quality numbers into human readable strings
        qual_strings = []
        for bitmask in lc.quality:
            flag_str_list = KeplerQualityFlags.decode(bitmask)
            if len(flag_str_list) == 0:
                qual_strings.append(' ')
            if len(flag_str_list) == 1:
                qual_strings.append(flag_str_list[0])
            if len(flag_str_list) > 1:
                qual_strings.append("; ".join(flag_str_list))

        # Convert time into human readable strings, breaks with NaN time
        # See https://github.com/KeplerGO/lightkurve/issues/116
        if (self.time == self.time).all():
            human_time = self.astropy_time.isot[lc_cad_matches]
        else:
            human_time = [' '] * n_lc_cad

        # Each data source will later become a hover-over tooltip
        source = ColumnDataSource(data=dict(
            time=lc.time,
            time_iso=human_time,
            flux=lc.flux,
            cadence=lc.cadenceno,
            quality_code=lc.quality,
            quality=np.array(qual_strings)))

        # Provide extra metadata in the title
        if self.mission == 'K2':
            title = "Quicklook lightcurve for EPIC {} (K2 Campaign {})".format(
                self.keplerid, self.campaign)
        elif self.mission == 'Kepler':
            title = "Quicklook lightcurve for KIC {} (Kepler Quarter {})".format(
                self.keplerid, self.quarter)

        # Figure 1 shows the lightcurve with steps, tooltips, and vertical line
        fig1 = figure(title=title, plot_height=300, plot_width=600,
                      tools="pan,wheel_zoom,box_zoom,save,reset")
        fig1.yaxis.axis_label = ytitle
        fig1.xaxis.axis_label = 'Time - 2454833 days [BKJD]'
        fig1.step('time', 'flux', line_width=1, color='gray', source=source,
                  nonselection_line_color='gray', mode="center")

        r = fig1.circle('time', 'flux', source=source, fill_alpha=0.3, size=8,
                        line_color=None, selection_color="firebrick",
                        nonselection_fill_alpha=0.0, nonselection_line_color=None,
                        nonselection_line_alpha=0.0, fill_color=None,
                        hover_fill_color="firebrick", hover_alpha=0.9,
                        hover_line_color="white")

        fig1.add_tools(HoverTool(tooltips=[("Cadence", "@cadence"),
                                           ("Time (BKJD)", "@time{0,0.000}"),
                                           ("Time (ISO)", "@time_iso"),
                                           ("Flux", "@flux"),
                                           ("Quality Code", "@quality_code"),
                                           ("Quality Flag", "@quality")],
                                 renderers=[r],
                                 mode='mouse',
                                 point_policy="snap_to_data"))
        # Vertical line to indicate the cadence shown in Fig 2
        vert = Span(location=0, dimension='height', line_color='firebrick',
                    line_width=4, line_alpha=0.5)
        fig1.add_layout(vert)

        # Figure 2 shows the Target Pixel File stamp with log screen stretch
        fig2 = figure(plot_width=300, plot_height=300,
                      tools="pan,wheel_zoom,box_zoom,save,reset",
                      title='Pixel data (CCD {}.{})'.format(
                          self.module, self.output))
        fig2.yaxis.axis_label = 'Pixel Row Number'
        fig2.xaxis.axis_label = 'Pixel Column Number'

        pedestal = np.nanmin(self.flux[lc_cad_matches, :, :])
        stretch_dims = np.prod(self.flux[lc_cad_matches, :, :].shape)
        screen_stretch = self.flux[lc_cad_matches, :, :].reshape(stretch_dims) - pedestal
        screen_stretch = screen_stretch[np.isfinite(screen_stretch)]  # ignore NaNs
        screen_stretch = screen_stretch[screen_stretch > 0.0]
        vlo = np.min(screen_stretch)
        vhi = np.max(screen_stretch)
        vstep = (np.log10(vhi) - np.log10(vlo)) / 300.0  # assumes counts >> 1.0!
        lo, med, hi = np.nanpercentile(screen_stretch, [1, 50, 95])
        color_mapper = LogColorMapper(palette="Viridis256", low=lo, high=hi)

        fig2_dat = fig2.image([self.flux[0, :, :] - pedestal], x=self.column,
                              y=self.row, dw=self.shape[2], dh=self.shape[1],
                              dilate=False, color_mapper=color_mapper)

        # The figures appear before the interactive widget sliders
        show(row(fig1, fig2), notebook_handle=True)

        # The widget sliders call the update function each time
        def update(cadence, log_stretch):
            """Function that connects to the interact widget slider values"""
            fig2_dat.glyph.color_mapper.high = 10**log_stretch[1]
            fig2_dat.glyph.color_mapper.low = 10**log_stretch[0]
            if cadence not in missing_cadences:
                index_val = cadence_lookup[cadence]
                vert.update(line_alpha=0.5)
                if self.time[index_val] == self.time[index_val]:
                    vert.update(location=self.time[index_val])
                else:
                    vert.update(line_alpha=0.0)
                fig2_dat.data_source.data['image'] = [self.flux[index_val, :, :]
                                                      - pedestal]
            else:
                vert.update(line_alpha=0)
                fig2_dat.data_source.data['image'] = [self.flux[0, :, :] * np.NaN]
            push_notebook()

        # Define the widgets that enable the interactivity
        play = widgets.Play(interval=10, value=min_cadence, min=min_cadence,
                            max=max_cadence, step=1, description="Press play",
                            disabled=False)
        play.show_repeat, play._repeat = False, False
        cadence_slider = widgets.IntSlider(
            min=min_cadence, max=max_cadence,
            step=1, value=min_cadence, description='Cadence',
            layout=widgets.Layout(width='40%', height='20px'))
        screen_slider = widgets.FloatRangeSlider(
            value=[np.log10(lo), np.log10(hi)],
            min=np.log10(vlo),
            max=np.log10(vhi),
            step=vstep,
            description='Pixel Stretch (log)',
            style={'description_width': 'initial'},
            continuous_update=False,
            layout=widgets.Layout(width='30%', height='20px'))
        widgets.jslink((play, 'value'), (cadence_slider, 'value'))
        ui = widgets.HBox([play, cadence_slider, screen_slider])
        out = widgets.interactive_output(update, {'cadence': cadence_slider,
                                                  'log_stretch': screen_slider})
        display(ui, out)

    def get_bkg_lightcurve(self, aperture_mask=None):
        aperture_mask = self._parse_aperture_mask(aperture_mask)
        return LightCurve(time=self.time,
                          time_format='bkjd',
                          time_scale='tdb',
                          flux=np.nansum(self.flux_bkg[:, aperture_mask], axis=1),
                          flux_err=self.flux_bkg_err)

    def to_fits(self, output_fn=None, overwrite=False):
        """Writes the TPF to a FITS file on disk."""
        if output_fn is None:
            output_fn = "{}-targ.fits".format(self.keplerid)
        self.hdu.writeto(output_fn, overwrite=overwrite, checksum=True)

    def _get_hdu(image, extension):
        """Checks if an image is a single FITS image, or a FITS file,
        and returns the appropriate PrimaryHDU.

        Attributes
        ----------
        image : fits.ImageHDU or fits.HDUList object
            FITS filename path or ImageHDU object to get the data from.
        extension: integer
            Number of the file extension containing data, depends on the file
            type and source.

        Returns
        -------
        hdu : astropy.PrimaryHDU
            PrimaryHDU of the image inputted.
        """
        if isinstance(image, fits.ImageHDU):
            hdu = image
        elif isinstance(image, fits.HDUList):
            hdu = image[extension]
        else:
            hdu = fits.open(image)[extension]
        return hdu

    def _get_pos_corrs(mid_img, hdu, position, extension):
        """Calculates the position correction values (both in row and column) and
        WCS for an image relative to the reference image, defined as the middle
        cadence of the FITS file.

        Attributes
        ----------
        hdu : astropy.PrimaryHDU
            PrimaryHDU of the image being looked at.
        mid_img : fits.ImageHDU
            Reference image from the FITS file.
        position : astropy.SkyCoord
            Position around which to cut out pixels.
        extension : integer
            Number of the file extension containing data, depends on the file
            type and source.

        Returns
        -------
        poscorr1 :  float32
            Position correction in the vertical direction (column).
        poscorr2 :  float32
            Position correction in the horizontal direction (row).
        wcs1 :  astropy.wcs.WCS
            WCS object for this hdu.
        column : integer
            Column number of the center pixel.
        row : integer
            Row number of the center pixel.
        ractr :
            Right ascension of the center of the center pixel.
        decctr:
            Declination of the center of the center pixel.
        """
        # Calculate reference WCS coords from the middle image to use later to
        # do pos_corr calcs. Get the middle pixel column and row.
        mid_hdu = KeplerTargetPixelFile._get_hdu(mid_img, extension)
        wcs = WCS(mid_hdu)
        pixelpos = skycoord_to_pixel(position, wcs=wcs)
        column, row = int(np.round(pixelpos[0])), int(np.round(pixelpos[1]))

        # Calculate the ra and dec of the center pixel of the middle image
        skyposctr = pixel_to_skycoord(column, row, wcs=wcs)
        ractr = skyposctr.ra.deg
        decctr = skyposctr.dec.deg

        # Get positional shift of the image compared to the reference file
        wcs1 = WCS(hdu)
        pixelpos1 = skycoord_to_pixel(position, wcs=wcs1)
        poscorr1 = pixelpos1[0] - pixelpos[0]
        poscorr2 = pixelpos1[1] - pixelpos[1]

        return [wcs1, poscorr1, poscorr2, column, row, ractr, decctr]

    @staticmethod
    def from_fits_images(images, position=None, size=(10, 10), extension=None,
                         target_id="unnamed-target", **kwargs):
        """Creates a new Target Pixel File from a set of images.

        This method is intended to make it easy to cut out targets from
        Kepler/K2 "superstamp" regions or TESS FFI images.

        Attributes
        ----------
        images : list of str, or list of fits.ImageHDU objects
            Sorted list of FITS filename paths or ImageHDU objects to get
            the data from.
        position : astropy.SkyCoord
            Position around which to cut out pixels.
        size : (int, int)
            Dimensions (cols, rows) to cut out around `position`.
        extension : int or str
            If `images` is a list of filenames, provide the extension number
            or name to use. Default: 0.
        target_id : int or str
            Unique identifier of the target to be recorded in the TPF.
        **kwargs : dict
            Extra arguments to be passed to the `KeplerTargetPixelFile` constructor.

        Returns
        -------
        tpf : KeplerTargetPixelFile
            A new Target Pixel File assembled from the images.
        """
        if extension is None:
            if isinstance(images[0], str) and images[0].endswith("ffic.fits"):
                extension = 1  # TESS FFIs have the image data in extension #1
            else:
                extension = 0  # Default is to use the primary HDU

        factory = KeplerTargetPixelFileFactory(n_cadences=len(images),
                                               n_rows=size[0],
                                               n_cols=size[1],
                                               target_id=target_id)
        # Find middle image to use as a reference
        mid_img = images[int(len(images)/2)-1]

        for idx, img in tqdm(enumerate(images), total=len(images)):
            hdu = KeplerTargetPixelFile._get_hdu(img, extension)
            if idx == 0:  # Get default keyword values from the first image
                factory.keywords = hdu.header
            if position is None:
                cutout = hdu
            else:
                cutout = Cutout2D(hdu.data, position, wcs=WCS(hdu.header),
                                  size=size, mode='partial')

            wcs, pos_corr1, pos_corr2, col, row, ractr, decctr = \
                KeplerTargetPixelFile._get_pos_corrs(mid_img, hdu, position, extension)
            # Add calculated pos corr shifts to the keywords dictionary
            hdu.header['POSCORR1'] = pos_corr1
            hdu.header['POSCORR2'] = pos_corr2

            factory.add_cadence(frameno=idx, wcs=wcs, flux=cutout.data, header=hdu.header)

        tpfsize = size[0] # Use column value assuming a square TPF
        if (tpfsize % 2 == 0): # Make sure tpfsize is odd to center the star
             tpfsize += 1

        # Override the defaults where necessary, and pass into the header generating functions
        header_info = {}
        header_info['OBJECT'] = factory.target_id
        header_info['KEPLERID'] = factory.target_id
        header_info['RA_OBJ'] = factory.keywords["RA_OBJ"]
        header_info['DEC_OBJ'] = factory.keywords["DEC_OBJ"]

        ext1_info = {}
        ext1_info['TFORM4'] = '{}J'.format(size[0]*size[1])
        ext1_info['TDIM4'] = '({},{})'.format(size[0],size[1])

        cd11 = factory.keywords['CD1_1']
        cd12 = factory.keywords['CD1_2']
        cd21 = factory.keywords['CD2_1']
        cd22 = factory.keywords['CD2_2']
        ext1_info['11PC5'] = -1.0*cd11/0.001102672560321 # hard coded from the template file
        ext1_info['12PC5'] = -1.0*cd12/0.001102672560321
        ext1_info['21PC5'] = cd21/0.001102672560321
        ext1_info['22PC5'] = cd22/0.001102672560321

        for m in [4, 5, 6, 7, 8, 9]:
            if m > 4:
                header_info["TFORM{}".format(m)] = '{}E'.format(size[0]*size[1])
            ext1_info['TDIM{}'.format(m)] = '({},{})'.format(size[0],size[1])
            ext1_info['1CRV{}P'.format(m)] = col - int((tpfsize-1)/2) + factory.keywords['CRVAL1P']
            ext1_info['2CRV{}P'.format(m)] = row - int((tpfsize-1)/2) + factory.keywords['CRVAL2P']
            ext1_info['1CRPX{}'.format(m)] = (tpfsize + 1)/2
            ext1_info['2CRPX{}'.format(m)] = (tpfsize + 1)/2

        ext_info = {"header_info": header_info, "ext1_info": ext1_info}
        return factory.get_tpf(ext_info)

class KeplerTargetPixelFileFactory(object):
    """Class to create a KeplerTargetPixelFile."""

    def __init__(self, n_cadences, n_rows, n_cols, target_id="unnamed-target",
                 keywords={}):
        self.n_cadences = n_cadences
        self.n_rows = n_rows
        self.n_cols = n_cols
        self.target_id = target_id
        self.keywords = keywords

        # Initialize the 3D data structures
        self.raw_cnts = np.empty((n_cadences, n_rows, n_cols), dtype='int')
        self.flux = np.empty((n_cadences, n_rows, n_cols), dtype='float32')
        self.flux_err = np.empty((n_cadences, n_rows, n_cols), dtype='float32')
        self.flux_bkg = np.empty((n_cadences, n_rows, n_cols), dtype='float32')
        self.flux_bkg_err = np.empty((n_cadences, n_rows, n_cols), dtype='float32')
        self.cosmic_rays = np.empty((n_cadences, n_rows, n_cols), dtype='float32')

        # Set 3D data defaults
        self.raw_cnts[:, :, :] = -1
        self.flux[:, :, :] = np.nan
        self.flux_err[:, :, :] = np.nan
        self.flux_bkg[:, :, :] = np.nan
        self.flux_bkg_err[:, :, :] = np.nan
        self.cosmic_rays[:, :, :] = np.nan

        # Initialize the 1D data structures
        self.mjd = np.zeros(n_cadences, dtype='float64')
        self.time = np.zeros(n_cadences, dtype='float64')
        self.timecorr = np.zeros(n_cadences, dtype='float32')
        self.cadenceno = np.zeros(n_cadences, dtype='int')
        self.quality = np.zeros(n_cadences, dtype='int')
        self.pos_corr1 = np.zeros(n_cadences, dtype='float32')
        self.pos_corr2 = np.zeros(n_cadences, dtype='float32')

    def add_cadence(self, frameno, wcs=None, raw_cnts=None, flux=None, flux_err=None,
                    flux_bkg=None, flux_bkg_err=None, cosmic_rays=None,
                    header={}):
        """Populate the data for a single cadence."""
        # 2D-data
        for col in ['raw_cnts', 'flux', 'flux_err', 'flux_bkg',
                    'flux_bkg_err', 'cosmic_rays']:
            if locals()[col] is not None:
                vars(self)[col][frameno] = locals()[col]
        # 1D-data
        if 'TSTART' in header and 'TSTOP' in header:
            self.time[frameno] = (header['TSTART'] + header['TSTOP']) / 2.
        if 'TIMECORR' in header:
            self.timecorr[frameno] = header['TIMECORR']
        if 'CADENCEN' in header:
            self.cadenceno[frameno] = header['CADENCEN']
        if 'QUALITY' in header:
            self.quality[frameno] = header['QUALITY']
        if 'POSCORR1' in header:
            self.pos_corr1[frameno] = header['POSCORR1']
        if 'POSCORR2' in header:
            self.pos_corr2[frameno] = header['POSCORR2']

    def get_tpf(self, ext_info={}):
        """Returns a KeplerTargetPixelFile object."""
        return KeplerTargetPixelFile(self._hdulist(ext_info), **kwargs)

    def _hdulist(self, ext_info={}):
        """Returns an astropy.io.fits.HDUList object."""
        return fits.HDUList([self._make_primary_hdu(ext_info.get('header_info')),
                             self._make_target_extension(ext_info.get('ext1_info')),
                             self._make_aperture_extension()])

    def _header_template(self, extension):
        """Returns a template `fits.Header` object for a given extension."""
        template_fn = os.path.join(PACKAGEDIR, "data",
                                   "tpf-ext{}-header.txt".format(extension))
        return fits.Header.fromtextfile(template_fn)

    def _make_primary_hdu(self, header):
        """Returns the primary extension (#0)."""
        hdu = fits.PrimaryHDU()
        # Copy the default keywords from a template file from the MAST archive
        tmpl = self._header_template(0)
        for kw in tmpl:
            hdu.header[kw] = (tmpl[kw], tmpl.comments[kw])
        # Override the defaults where necessary
        hdu.header['ORIGIN'] = "Unofficial data product"
        hdu.header['DATE'] = datetime.datetime.now().strftime("%Y-%m-%d")
        hdu.header['CREATOR'] = "lightkurve"
        hdu.header['OBJECT'] = self.target_id
        hdu.header['KEPLERID'] = self.target_id
        hdu.header['RA_OBJ'] = self.keywords['RA_OBJ']
        hdu.header['DEC_OBJ'] = self.keywords['DEC_OBJ']

        # Override defaults using data calculated in from_fits_images
        for kw in header_info.keys():
            hdu.header[kw] = header_info[kw]
        # Empty a bunch of keywords rather than having incorrect info
        for kw in ["PROCVER", "FILEVER", "CHANNEL", "MODULE", "OUTPUT",
                   "TIMVERSN", "CAMPAIGN", "DATA_REL", "TTABLEID"]:
            hdu.header[kw] = ""
        return hdu

    def _make_target_extension(self, ext1_info):
        """Create the 'TARGETTABLES' extension (i.e. extension #1)."""
        # Turn the data arrays into fits columns and initialize the HDU
        coldim = '({},{})'.format(self.n_cols, self.n_rows)
        eformat = '{}E'.format(self.n_rows * self.n_cols)
        jformat = '{}J'.format(self.n_rows * self.n_cols)
        cols = []
        cols.append(fits.Column(name='TIME', format='D', unit='BJD - 2454833',
                                array=self.time))
        cols.append(fits.Column(name='TIMECORR', format='E', unit='D',
                                array=self.timecorr))
        cols.append(fits.Column(name='CADENCENO', format='J',
                                array=self.cadenceno))
        cols.append(fits.Column(name='RAW_CNTS', format=jformat,
                                unit='count', dim=coldim,
                                array=self.raw_cnts))
        cols.append(fits.Column(name='FLUX', format=eformat,
                                unit='e-/s', dim=coldim,
                                array=self.flux))
        cols.append(fits.Column(name='FLUX_ERR', format=eformat,
                                unit='e-/s', dim=coldim,
                                array=self.flux_err))
        cols.append(fits.Column(name='FLUX_BKG', format=eformat,
                                unit='e-/s', dim=coldim,
                                array=self.flux_bkg))
        cols.append(fits.Column(name='FLUX_BKG_ERR', format=eformat,
                                unit='e-/s', dim=coldim,
                                array=self.flux_bkg_err))
        cols.append(fits.Column(name='COSMIC_RAYS', format=eformat,
                                unit='e-/s', dim=coldim,
                                array=self.cosmic_rays))
        cols.append(fits.Column(name='QUALITY', format='J',
                                array=self.quality))
        cols.append(fits.Column(name='POS_CORR1', format='E', unit='pixels',
                                array=self.pos_corr1))
        cols.append(fits.Column(name='POS_CORR2', format='E', unit='pixels',
                                array=self.pos_corr2))
        coldefs = fits.ColDefs(cols)
        hdu = fits.BinTableHDU.from_columns(coldefs)

        # Set the header with defaults
        template = self._header_template(1)
        for kw in template:
            if kw not in ['XTENSION', 'NAXIS1', 'NAXIS2', 'CHECKSUM', 'BITPIX']:
                try:
                    hdu.header[kw] = (self.keywords[kw],
                                      self.keywords.comments[kw])
                except KeyError:
                    hdu.header[kw] = (template[kw],
                                      template.comments[kw])
        # Override defaults using data calculated in from_fits_images
        for kw in ext1_info.keys():
            hdu.header[kw] = ext1_info[kw]

        return hdu

    def _make_aperture_extension(self):
        """Create the aperture mask extension (i.e. extension #2)."""
        mask = 3 * np.ones((self.n_rows, self.n_cols), dtype='int32')
        hdu = fits.ImageHDU(mask)

        # Set the header from the template TPF again
        template = self._header_template(2)
        for kw in template:
            if kw not in ['XTENSION', 'NAXIS1', 'NAXIS2', 'CHECKSUM', 'BITPIX']:
                try:
                    hdu.header[kw] = (self.keywords[kw],
                                      self.keywords.comments[kw])
                except KeyError:
                    hdu.header[kw] = (template[kw],
                                      template.comments[kw])

        # Override the defaults where necessary
        for keyword in ['CTYPE1','CTYPE2','CRPIX1','CRPIX2', 'CRVAL1','CRVAL2', 'CUNIT1',
                        'CUNIT2', 'CDELT1', 'CDELT2','PC1_1','PC1_2','PC2_1','PC2_2']:
                hdu.header[keyword] = "" #override wcs keywords
        hdu.header['EXTNAME'] = 'APERTURE'
        return hdu
