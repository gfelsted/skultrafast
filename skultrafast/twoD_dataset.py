from collections import defaultdict
from lmfit.minimizer import MinimizerResult
import os
from pathlib import Path
from typing import Dict, Iterable, List, Literal, Optional, Tuple, Union, Any

import attr
import lmfit
import matplotlib.pyplot as plt
import numpy as np
from numpy.polynomial import Polynomial
from scipy.interpolate import RegularGridInterpolator
from scipy.ndimage import gaussian_filter, uniform_filter
from scipy.stats import linregress
from statsmodels.api import OLS, WLS, add_constant

from skultrafast import dv, plot_helpers
from skultrafast.dataset import TimeResSpec
from skultrafast.twoD_plotter import TwoDimPlotter
from skultrafast.utils import inbetween, LinRegResult
from skultrafast.base_funcs.lineshapes import gauss2d, two_gauss2D_shared, two_gauss2D

PathLike = Union[str, bytes, os.PathLike]


@attr.s(auto_attribs=True)
class SingleCLSResult:
    """Result of a single CLS fit."""
    pump_wn: np.ndarray
    """Pump wavenumbers."""
    max_pos: np.ndarray
    """Maximum positions for each pump-slice."""
    max_pos_err: np.ndarray
    """Standard error of the maximum positions. Nan if not available"""
    slope: float
    """Slope of the linear fit."""
    reg_result: Any
    """Result of the linear regression using statsmodels."""
    recentered_pump_wn: np.ndarray
    """Recentered pump wavenumbers by mean subtraction. Used in the linear regression."""
    linear_fit: np.ndarray
    """Linear fit of the CLS data."""


@attr.s(auto_attribs=True)
class FFCFResult:
    """Baseclass for FFCF determination methods.

    For backwards compatibility, the values are always called slopes"""

    wt: np.ndarray
    """Wait times."""
    slopes: np.ndarray
    """Values """
    slope_errors: Optional[np.ndarray] = None
    exp_fit_result_: Optional[lmfit.model.ModelResult] = None

    def exp_fit(self, start_taus: List[float], use_const=True, use_weights=True):
        mod = lmfit.models.ConstantModel()
        vals = {}

        for i, v in enumerate(start_taus):
            prefix = 'abcdefg'[i] + '_'
            mod += lmfit.models.ExponentialModel(prefix=prefix)
            vals[prefix + 'decay'] = v
            vals[prefix + 'amplitude'] = 0.5 / len(start_taus)

        for p in mod.param_names:
            if p.endswith('decay'):
                mod.set_param_hint(p, min=0)
            if p.endswith('amplitude'):
                mod.set_param_hint(p, min=0)
        if use_const:
            c = max(np.min(self.slopes), 0)
        else:
            c = 0
            mod.set_param_hint('c', vary=False)

        if self.slope_errors is not None and use_weights:
            weights = 1 / np.array(self.slope_errors)
        else:
            weights = None
        res = mod.fit(self.slopes, weights=weights, x=self.wt, c=c, **vals)
        self.exp_fit_result_ = res
        return res

    def plot_cls(self, ax=None, model_style: Dict = {}, symlog=False, **kwargs):
        if ax is None:
            ax = plt.gca()
        ec = ax.errorbar(self.wt, self.slopes, self.slope_errors, **kwargs)
        if symlog:
            ax.set_xscale('symlog', linthresh=1)
        plot_helpers.lbl_trans(ax=ax, use_symlog=symlog)

        ax.set(xlabel=plot_helpers.time_label, ylabel='Slope')
        m_line = None
        if self.exp_fit_result_:
            xu = np.linspace(np.min(self.wt), np.max(self.wt), 300)
            yu = self.exp_fit_result_.eval(x=xu)
            style = dict(color='k', zorder=1.8)
            if model_style:
                style.update(model_style)
            m_line = ax.plot(xu, yu, **style)
        return ec, m_line


@attr.s(auto_attribs=True, kw_only=True)
class CLSResult(FFCFResult):
    """
    Class holding the data of CLS-analysis. Has methods to analyze and plot them.
    """
    intercepts: np.ndarray
    """Contains the intercepts, useful for plotting mostly"""
    intercept_errors: Optional[np.ndarray]
    """Errors of the intercepts"""
    lines: List[np.ndarray]
    """Contains the x and y, yerr-values used for the linear fit"""

    exp_fit_result_: Optional[lmfit.model.ModelResult] = None


@attr.s(auto_attribs=True)
class DiagResult:
    diag: np.ndarray
    """Contains the diagonal signals of the 2d-spectra"""
    antidiag: np.ndarray
    """Contains the antidiagonal signals of the 2d-spectra"""
    diag_coords: np.ndarray
    """Contains the coordinates of the diagonal signals"""
    antidiag_coords: np.ndarray
    """Contains the coordinates of the antidiagonal signals"""
    offset: float
    """The offset of the diagonal signals"""
    p: float
    """The position crossing the diagonals"""


@attr.dataclass
class ExpFit2DResult:
    minimizer: MinimizerResult
    """Lmfit minimizer result"""
    model: 'TwoDim'
    """The fit data"""
    residuals: np.ndarray
    """The residuals of the fit"""
    das: np.ndarray
    """The decay amplitudes aka the DAS of the 2D-spectra"""
    basis: np.ndarray
    """The basis functions used for the fit"""
    taus: np.ndarray
    """The decay times of the fit"""


@attr.s(auto_attribs=True, kw_only=True)
class GaussResult(FFCFResult):
    """
    A dataclass to hold the results of the Gaussian fit.
    """
    results: List[lmfit.model.ModelResult]
    """List of lmfit results from the gaussian fits"""
    fit_out: 'TwoDim'
    """TwoDim object with the fit data, useful for plotting"""


@attr.s(auto_attribs=True)
class TwoDim:
    """
    Dataset for an two dimensional dataset. Requires the t- (waiting times),the
    probe- and pump-axes in addition to the three dimensional spec2d data.
    """

    t: np.ndarray
    "Array of the waiting times"
    pump_wn: np.ndarray
    "Array with the pump-wavenumbers"
    probe_wn: np.ndarray
    "Array with the probe-wavenumbers"
    spec2d: np.ndarray
    "Array with the data, shape must be (t.size, wn_probe.size, wn_pump.size)"
    info: Dict = {}
    "Meta Info"
    single_cls_result_: Optional[SingleCLSResult] = None
    "Contains the data from a Single CLS analysis"
    cls_result_: Optional[CLSResult] = None
    "Contains the data from a CLS analysis"
    plot: 'TwoDimPlotter' = attr.Factory(TwoDimPlotter, True)  # typing: Ignore
    "Plot object offering plotting methods"
    interpolator_: Optional[RegularGridInterpolator] = None  # typing: Ignore
    "Contains the interpolator for the 2d-spectra"
    exp_fit_result_: Optional[ExpFit2DResult] = None
    "Contains the result of the exponential fit"

    def _make_int(self):
        intp = RegularGridInterpolator((self.t, self.probe_wn, self.pump_wn),
                                       self.spec2d,
                                       bounds_error=False)
        return intp

    def __attrs_post_init__(self):
        n, m, k = self.t.size, self.probe_wn.size, self.pump_wn.size
        if self.spec2d.shape != (n, m, k):
            raise ValueError("Data shape not equal to t, wn_probe, wn_pump shape"
                             f"{self.spec2d.shape} != {n, m, k}")

        self.spec2d = self.spec2d.copy()
        self.probe_wn = self.probe_wn.copy()
        self.pump_wn = self.pump_wn.copy()
        self.t = self.t.copy()

        i1 = np.argsort(self.pump_wn)
        self.pump_wn = self.pump_wn[i1]
        i2 = np.argsort(self.probe_wn)
        self.probe_wn = self.probe_wn[i2]
        self.spec2d = self.spec2d[:, :, i1][:, i2, :]

    def copy(self) -> 'TwoDim':
        """
        Makes a copy of the dataset.
        """
        cpy = TwoDim(self.t, self.pump_wn, self.probe_wn, self.spec2d)
        cpy.plot = TwoDimPlotter(cpy)  # typing: ignore
        return cpy

    def t_idx(self, t: Union[float, Iterable[float]]) -> Union[int, List[int]]:
        """Return nearest idx to nearest time value"""
        return dv.fi(self.t, t)

    def t_d(self, t) -> np.ndarray:
        """Return the dataset nearest to the given time t"""
        return self.spec2d[self.t_idx(t), :, :]

    def data_at(self,
                t: Optional[float] = None,
                probe_wn: Optional[float] = None,
                pump_wn: Optional[float] = None) -> np.ndarray:
        """
        Extracts the data at given coordinates.
        """
        spec2d = self.spec2d
        if t is not None:
            t_idx = self.t_idx(t)
            spec2d = spec2d[t_idx, ...]
        if probe_wn is not None:
            pr_idx = self.probe_idx(probe_wn)
            spec2d = spec2d[..., pr_idx, :]
        if pump_wn is not None:
            pu_idx = self.pump_idx(pump_wn)
            spec2d = spec2d[..., pu_idx]
        return spec2d

    def probe_idx(self, wn: Union[float, Iterable[float]]) -> Union[int, List[int]]:
        """Return nearest idx to nearest probe_wn value"""
        return dv.fi(self.probe_wn, wn)

    def pump_idx(self, wn: Union[float, Iterable[float]]) -> Union[int, List[int]]:
        """Return nearest idx to nearest pump_wn value"""
        return dv.fi(self.pump_wn, wn)

    def select_range(self,
                     pump_range: Tuple[float, float],
                     probe_range: Tuple[float, float],
                     invert: bool = False) -> 'TwoDim':
        """
        Return a dataset containing only the selected region.
        """
        pu_idx = inbetween(self.pump_wn, min(pump_range), max(pump_range))
        pr_idx = inbetween(self.probe_wn, min(probe_range), max(probe_range))

        if invert:
            pu_idx = not pu_idx
            pr_idx = not pr_idx

        ds = self.copy()
        ds.spec2d = ds.spec2d[:, pr_idx, :][:, :, pu_idx]
        ds.pump_wn = ds.pump_wn[pu_idx]
        ds.probe_wn = ds.probe_wn[pr_idx]
        return ds

    def select_t_range(self, t_min: float = -np.inf, t_max: float = np.inf) -> 'TwoDim':
        """"
        Returns a dataset only containing the data within given time limits.
        """
        idx = inbetween(self.t, t_min, t_max)
        ds = self.copy()
        ds.t = ds.t[idx]
        ds.spec2d = ds.spec2d[idx, :, :]
        return ds

    def integrate_pump(self,
                       lower: float = -np.inf,
                       upper: float = np.inf) -> TimeResSpec:
        """
        Calculate and return 1D Time-resolved spectra for given range.

        Uses trapezoidal integration.

        Parameters
        ----------
        lower : float
            Lower pump wl
        upper : float
            upper pump wl

        Returns
        -------
        TimeResSpec
            The corresponding 1D Dataset
        """
        pu_idx = inbetween(self.pump_wn, lower, upper)
        data = np.trapz(self.spec2d[:, :, pu_idx], self.pump_wn[pu_idx], axis=-1)
        return TimeResSpec(self.probe_wn, self.t, data, freq_unit='cm')

    def single_cls(
        self,
        t: float,
        pr_range: Union[float, Tuple[float, float]] = 9.0,
        pu_range: Union[float, Tuple[float, float]] = 7.0,
        mode: Literal['neg', 'pos'] = 'neg',
        method: Literal['com', 'quad', 'fit', 'log_quad', 'skew_fit'] = 'com'
    ) -> SingleCLSResult:
        """
        Calculate the CLS for single 2D spectrum.

        Parameters
        ----------
        t : float
            Delay time of the spectrum to analyse
        pr_range : float or float, optional
            How many wavenumbers away from the maximum to use for
            determining the exact position, by default 9, resulting 
            a total range of 18 wavenumbers. Also accepts a tuple,
            which is interpreted as (lower, upper) range.
        pu_range : float, optional
            The range around the pump-maxima used for calculating
            the CLS. If given a float, the range is calculated
            as (max - pu_range, max + pu_range). If given a tuple,
            it is interpreted as (lower, upper) range.
        mode : ('neg', 'pos'), optional
            negative or positive maximum, by default 'neg'
        method: ('com', 'quad', 'fit')
            Selects the method used for determination of the
            maximum signal. `com` uses the center-of-mass,
            `quad` uses a quadratic fit and `fit` uses
            a gaussian fit.

        Returns
        -------
        Returns SingleCLSResult object with attributes:
                        pump_wn
                        max_pos
                        max_pos_err
                        slope
                        reg_result
                        recentered_pump_wn
                        linear_fit
        """
        pu = self.pump_wn
        pr = self.probe_wn
        spec = self.spec2d[self.t_idx(t), :, :].T
        if mode == 'pos':
            spec = -spec
        pu_max = pu[np.argmin(np.min(spec, 1))]
        if not isinstance(pu_range, tuple):
            pu_idx = (pu < pu_max + pu_range) & (pu > pu_max - pu_range)
        else:
            pu_idx = inbetween(pu, pu_range[0], pu_range[1])
        x = pu[pu_idx] - pu[pu_idx].mean()
        spec = spec[pu_idx, :]
        l = []
        for s in spec:
            m = np.argmin(s)
            if not isinstance(pr_range, tuple):
                pr_max = pr[m]
                pr_idx = (pr < pr_max + pr_range) & (pr > pr_max - pr_range)
            else:
                pr_idx = inbetween(pr, pr_range[0], pr_range[1])
            cen_of_m = np.average(pr[pr_idx], weights=s[pr_idx])
            if method == 'fit':
                mod = lmfit.models.GaussianModel()
                mod.set_param_hint('center', min=pr[pr_idx].min(), max=pr[pr_idx].max())
                amp = np.trapz(s[pr_idx], pr[pr_idx])
                result = mod.fit(s[pr_idx],
                                 sigma=3,
                                 center=cen_of_m,
                                 amplitude=amp,
                                 x=pr[pr_idx])
                val, err = (result.params['center'].value, result.params['center'].stderr)
                if err is None:
                    err = np.nan
                l.append((val, err))
            elif method == 'quad':
                p: Polynomial = Polynomial.fit(pr[pr_idx], s[pr_idx], 2)  # type: ignore
                l.append((p.deriv().roots()[0], 1))
            elif method == 'log_quad':
                s_min = s[m]
                i2 = (s < s_min * 0.1)
                p = Polynomial.fit(pr[pr_idx & i2], np.log(-s[pr_idx & i2]),
                                   2)  # type: ignore
                l.append((p.deriv().roots()[0], 1))
            elif method == 'skew_fit':
                mod = lmfit.models.GaussianModel() + lmfit.models.LinearModel()
                amp = np.trapz(s[pr_idx], pr[pr_idx])
                result = mod.fit(s[pr_idx],
                                 sigma=3,
                                 center=cen_of_m,
                                 amplitude=amp,
                                 x=pr[pr_idx],
                                 slope=0,
                                 intercept=0)
                val, err = (result.params['center'].value, result.params['center'].stderr)
                if err is None:
                    err = np.nan
                l.append((val, err))

            else:
                l.append((cen_of_m, 1))

        y, yerr = np.array(l).T
        all_err_valid = np.isfinite(yerr).all()
        if all_err_valid:
            r = WLS(y, add_constant(x), weights=1 / yerr**2).fit()
        else:
            r = OLS(y, add_constant(x)).fit()
        
        ret = SingleCLSResult(pump_wn=x + pu[pu_idx].mean(),
                        max_pos=y,
                        max_pos_err=yerr,
                        slope=r.params[0],
                        reg_result=r,
                        recentered_pump_wn=x,
                        linear_fit=r.predict())
        
        self.single_cls_result_ = ret

        return ret

    def cls(self, **cls_args) -> CLSResult:
        """Calculates the CLS for all 2d-spectra. The arguments are given
        to the single cls function. Returns as `CLSResult`."""
        slopes, slope_errs = [], []
        lines = []
        intercept = []
        intercept_errs = []
        import joblib
        with joblib.Parallel(n_jobs=-1) as p:
            res: List[SingleCLSResult] = p(
                joblib.delayed(self.single_cls)(t, **cls_args) for t in self.t)
        for c in res:
            r = c.reg_result
            slopes.append(r.params[1])
            slope_errs.append(r.bse[1])
            lines += [np.column_stack((c.pump_wn, c.max_pos, c.max_pos_err, r.predict()))]
            intercept.append(r.params[0])
            intercept_errs.append(r.bse[0])
        ret = CLSResult(wt=self.t,
                        slopes=np.array(slopes),
                        slope_errors=np.array(slope_errs),
                        lines=lines,
                        intercepts=np.array(intercept),
                        intercept_errors=np.array(intercept_errs))
        self.cls_result_ = ret
        return ret

    def diag_and_antidiag(self,
                          t: float,
                          offset: Optional[float] = None,
                          p: Optional[float] = None) -> DiagResult:
        """
        Extracts the diagonal and anti-diagonal.

        Parameters
        ----------
        t: float
            Waiting time of the 2d-spectra from which the data is extracted.
        offset: float
            Offset of the diagonal, if none, it will we determined by the going through the signal
            minimum.
        p: float
            The point where the anti-diagonal crosses the diagonal. If none, it also goes through
            the signal minimum.

        Returns
        -------
        CLSResult
            Contains the diagonals, coordinates and points.
        """

        spec_i = self.t_idx(t)

        if self.interpolator_ is None:
            self.interpolator_ = self._make_int()

        d = self.spec2d[spec_i, ...].T

        if offset is None:
            offset = self.pump_wn[np.argmin(np.min(d, 1))] - self.probe_wn[np.argmin(
                np.min(d, 0))]
        if p is None:
            p = self.probe_wn[np.argmin(np.min(d, 0))]

        y_diag = self.probe_wn + offset
        y_antidiag = -self.probe_wn + 2*p + offset

        ts = self.t[spec_i] * np.ones_like(y_diag)
        diag = self.interpolator_(np.column_stack((ts, self.probe_wn, y_diag)))
        antidiag = self.interpolator_(np.column_stack((ts, self.probe_wn, y_antidiag)))

        res = DiagResult(
            diag=diag,
            antidiag=antidiag,
            diag_coords=y_diag,
            antidiag_coords=y_antidiag,
            offset=offset,
            p=p,
        )
        return res

    def pump_slice_amp(self, t: float, bg_correct: bool = True) -> np.ndarray:
        """"
        Calculates the pump-slice-amplitude for a given delay t.
        """
        d = self.spec2d[self.t_idx(t), :, :]
        diag = np.ptp(d, axis=0)
        if bg_correct:
            diag -= (diag[0] + diag[-1]) / 2
        return diag

    def apply_filter(self, kind: Literal['uniform', 'gaussian'], size, *args) -> 'TwoDim':
        """"
        Returns filtered dataset.

        Parameters
        ----------
        kind: str
            Which filter to use. Supported are uniform and gaussian.
        size: tuple[float, float, float]
            Kernel of the filter

        Returns
        -------
        TwoDim
            Filtered dataset.
        """
        filtered = self.copy()
        if len(size) == 2:
            size = (1, size[0], size[1])
        if kind == 'uniform':
            filtered.spec2d = uniform_filter(self.spec2d, size, mode='nearest')
        if kind == 'gaussian':
            filtered.spec2d = gaussian_filter(self.spec2d, size, mode='nearest')
        return filtered

    def save_txt(self, pname: PathLike, **kwargs):
        """
        Saves 2d-spectra as a text files a directory.

        Parameters
        ----------
        pname: PathLike
            Path to the file.
        kwargs:
            Additional arguments for the np.savetxt function.
        """
        p = Path(pname)
        if not p.is_dir() or p.mkdir(parents=True, exist_ok=True):
            raise ValueError(f'{p} is not a directory')
        for i in range(self.spec2d.shape[0]):
            tstr = f'{self.t[i]:.3f}ps'
            self.save_single_txt(p / f'wt_{tstr}.txt', i, **kwargs)

    def save_single_txt(self, fname: PathLike, i: int, **kwargs):
        """
        Save a single 2D spectra as a text file

        Parameters
        ----------
        fname: str
            The file name.
        i: int
            The index of the 2D spectra.
        kwargs:
            Additional arguments for the `np.savetxt` function.
        """
        arr = np.block([[0, self.pump_wn], [self.probe_wn[:, None], self.spec2d[i]]])
        np.savetxt(fname,
                   arr,
                   **kwargs,
                   header='# pump axis along rows, probe axis along columns')

    def background_correction(self,
                              excluded_range: Tuple[float, float],
                              deg: int = 3) -> None:
        """
        Fits and subtracts a background for each pump-frequency. Done for each
        waiting time. Does the subtraction inplace, e.g. modifies the dataset.

        Parameters
        ----------
        excluded_range: Tuple[float, float]
            The range of the pump axis which is excluded from the fit, e.g.
            contains the signal.
        deg: int
            Degree of the polynomial fit.
        Returns
        -------
        None
        """
        wn_range = ~inbetween(self.probe_wn, excluded_range[0], excluded_range[1])
        for ti in range(self.spec2d.shape[0]):
            for pi in range(self.spec2d.shape[2]):
                s = self.spec2d[ti, :, pi]
                back = s[wn_range]
                p = np.polyfit(self.probe_wn[wn_range], back, deg)
                s -= np.polyval(p, self.probe_wn)

    def get_minmax(self, t: float, com: int = 3) -> Dict[str, float]:
        """
        Returns the position of the minimum and maximum of the dataset at time t. If com > 0,
        it return the center of mass around the minimum and maximum. The com argument gives
        the number of points to be used for the center of mass.
        """
        from scipy.ndimage import maximum_position, minimum_position
        spec_i = self.spec2d[self.t_idx(t), :, :]
        min_pos = minimum_position(spec_i)
        max_pos = maximum_position(spec_i)
        if com > 0:
            idx = slice(min_pos[0] - com, min_pos[0] + com + 1)
            probe_min = np.average(self.probe_wn[idx], weights=spec_i.min(1)[idx])
            idx = slice(max_pos[0] - com, max_pos[0] + com + 1)
            probe_max = np.average(self.probe_wn[idx], weights=spec_i.max(1)[idx])
            idx = slice(min_pos[1] - com, min_pos[1] + com + 1)
            pump_min = np.average(self.pump_wn[idx], weights=spec_i.min(0)[idx])
            idx = slice(max_pos[1] - com, max_pos[1] + com + 1)
            pump_max = np.average(self.pump_wn[idx], weights=spec_i.max(0)[idx])
        else:
            probe_min = self.probe_wn[min_pos[0]]
            probe_max = self.probe_wn[max_pos[0]]
            pump_min = self.pump_wn[min_pos[1]]
            pump_max = self.pump_wn[max_pos[1]]
        psamax = self.pump_wn[self.pump_slice_amp(t).argmax()]
        return {
            'ProbeMin': probe_min,
            'ProbeMax': probe_max,
            'PSAMax': psamax,
            'PumpMin': pump_min,
            'PumpMax': pump_max,
            'Anh': probe_min - probe_max
        }

    def integrate_reg(self,
                      pump_range: Tuple[float, float],
                      probe_range: Tuple[float, float] = None) -> np.ndarray:
        """
        Integrates the 2D spectra over a given range, using the trapezoidal
        rule.

        Parameters
        ----------

        pump_range: tuple[float, float]
            The range of the pump axis to be integrated over.
        probe_range: tuple[float, float]
            The range of the probe axis to be integrated over. If None, the
            probe range is used.

        Returns
        -------
        np.ndarray
            The integrated spectral signal for all waiting times.
        """
        if probe_range is None:
            probe_range = pump_range
        pr = inbetween(self.probe_wn, min(probe_range), max(probe_range))
        reg = self.spec2d[:, pr, :]
        pu = inbetween(self.pump_wn, min(pump_range), max(pump_range))
        reg = reg[:, :, pu]
        s = np.trapz(reg, self.pump_wn[pu], axis=2)
        s = np.trapz(s, self.probe_wn[pr], axis=1)
        return s

    def fit_taus(self, taus: np.ndarray):
        """
        Given a set of decay times, fit the data to a sum of the exponentials.
        Used by the `fit_taus` method.
        """
        nt, npu, npr = self.spec2d.shape
        basis = np.exp(-self.t[:, None] / taus[None, :])
        coef = np.linalg.lstsq(basis, self.spec2d.reshape(nt, -1), rcond=None)
        model = basis @ coef[0]
        resi = self.spec2d.reshape(nt, -1) - model
        return coef[0].reshape(taus.size, npu, npr), basis, resi, model, taus

    def fit_das(self, taus, fix_last_decay=False) -> ExpFit2DResult:
        """
        Fit the data to a sum of exponentials (DAS), starting from the given decay
        constants. The results are stored in the `fit_exp_result` attribute.
        """

        params = lmfit.Parameters()
        for i, val in enumerate(taus):
            params.add(f'tau{i}', value=val, vary=True)
        if fix_last_decay:
            params['tau%d' % i].vary = False

        def fcn(params, res_only=True):
            tau_arr = np.array([params[f'tau{i}'].value for i in range(len(taus))])
            fit_res = self.fit_taus(tau_arr)
            if res_only:
                return fit_res[2]
            else:
                return fit_res

        mini = lmfit.Minimizer(fcn, params)
        res = mini.minimize()
        fit_res = fcn(res.params, res_only=False)
        resi = fit_res[2].reshape(self.spec2d.shape)
        model = fit_res[3].reshape(self.spec2d.shape)
        dsc = self.copy()
        dsc.spec2d = model
        self.fit_exp_result_ = ExpFit2DResult(minimizer=res,
                                              model=dsc,
                                              residuals=resi,
                                              das=fit_res[0],
                                              basis=fit_res[1],
                                              taus=fit_res[4])
        return self.fit_exp_result_

    def fit_gauss(self, mode='both') -> GaussResult:
        """
        Fits the 2D spectra using two gaussians peaks.
        """
        # from skultrafast.utils import gauss2D

        mm = self.get_minmax(0.3)
        psa = self.pump_slice_amp(0.3)
        gmod = lmfit.models.GaussianModel()
        gres = gmod.fit(psa, x=self.pump_wn, center=mm['PSAMax'], sigma=2)
        results = []
        val_dict: Dict[str, list] = defaultdict(list)
        fit_out = self.copy()

        mod = lmfit.Model(two_gauss2D_shared, independent_vars=['pu', 'pr'])
        mod.set_param_hint('x01',
                           min=self.pump_wn.min(),
                           max=self.pump_wn.max(),
                           value=mm['PumpMax'])
        spec = self.data_at(t=0.5)
        mod.set_param_hint('A0', max=0, value=spec.min())
        mod.set_param_hint('k', min=0, value=1, vary=False)
        mod.set_param_hint('ah', min=0, value=mm['Anh'])
        mod.set_param_hint('sigma_pu', min=0, value=gres.params['sigma'].value)
        mod.set_param_hint('sigma_pr', min=0, value=gres.params['sigma'].value / 2)
        mod.set_param_hint('corr', value=0.4, min=0, max=1)

        last_params: Union[dict, lmfit.Parameters] = {'k': 1, 'offset': 0}

        for i, t in enumerate(self.t):
            spec = self.data_at(t=t)
            res = mod.fit(spec, pu=self.pump_wn, pr=self.probe_wn, **last_params)
            results.append(res)
            p = res.params
            for pname in p:
                val_dict[pname].append(p[pname].value)
                err = p[pname].stderr or np.inf

                val_dict[pname + '_stderr'].append(err)
            fit_out.spec2d[i] = res.best_fit.reshape(self.spec2d.shape[1:])
            last_params = res.params.copy()

        val_dict_arr = {k: np.array(v) for k, v in val_dict.items()}
        return GaussResult(results=results,
                           fit_out=fit_out,
                           slopes=val_dict_arr['corr'],
                           slope_errors=val_dict_arr['corr_stderr'],
                           wt=self.t)
