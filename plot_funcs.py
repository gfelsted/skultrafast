# -*- coding: utf-8 *-*
units = {'x': ' nm', 'y': ' ps', 'z': '$\\Delta$OD'}
title = ""
import matplotlib.pyplot as plt
import numpy as np
import dv, data_io, zero_finding

#plt.rcParams['font.size']=9
#plt.rcParams['legend.fontsize'] = 'small'
#plt.rcParams['legend.borderpad'] = 0.1
#plt.rcParams['legend.columnspacing'] = 0.3
#plt.rcParams['legend.labelspacing'] = 0.3
plt.rcParams['legend.loc'] = 'best'

def plot_das(fitter, plot_fastest=0, plot_coh=False ,normed=False, sas=False):
    """Plots the decay-asscoiated  """        
    num_exp = fitter.num_exponentials
    #fitter.last_para[-num_exp:] = np.sort(fitter.last_para[-num_exp:])
    
    
    if plot_coh or not fitter.model_coh:
        ulim = fitter.num_exponentials
    else:
        ulim = -4

    llim = plot_fastest
    
    dat_to_plot= fitter.c[:, llim:ulim]
    if sas:
        dat_to_plot = -dat_to_plot.sum(1)[:,None]+np.cumsum(dat_to_plot, 1)
    if normed: 
        dat_to_plot = dat_to_plot/np.abs(dat_to_plot).max(0)
    plt.plot(fitter.wl, dat_to_plot, lw=2)
    plt.autoscale(1, tight=1)
    plt.axhline(0, color='grey', zorder=-10, ls='--')
    leg = np.round(fitter.last_para[1 + llim + fitter.model_disp:], 2)
    plt.legend([str(i)+ units['y'] for i in leg], labelspacing=0.25)
    plt.xlabel(units['x'])
    plt.ylabel(units['z'])
    if title:
        plt.title(title)
        
def plot_pol_das(fitter, plot_fastest=0, plot_coh=False, normed=False):    
    """Plots the decay-asscoiated spectra for polarized data"""        
    t_slice = fitter.model_disp+2
    fitter.last_para[t_slice:] = np.sort(fitter.last_para[t_slice:])
    fitter.res(fitter.last_para)
    
    if plot_coh and fitter.model_coh:
        ulim = fitter.num_exponentials
    else:
        ulim =- 4

    llim = plot_fastest
    
    dat_to_plot= fitter.c[:,llim:ulim]
    if normed: 
        dat_to_plot = dat_to_plot / np.abs(dat_to_plot).max(0)
    half_idx = dat_to_plot.shape[0]/2       
    p1 = plt.plot(fitter.wl, dat_to_plot[:half_idx, :], lw=2)
    p2 = plt.plot(fitter.wl, dat_to_plot[half_idx:, :], '--', lw=2)
    dv.equal_color(p1, p2)
    plt.autoscale(1, tight=1)
    plt.axhline(0, color='grey', zorder=-10, ls='--')
    leg = np.round(fitter.last_para[2 + llim + fitter.model_disp:], 2)
    plt.legend([str(i)+ units['y'] for i in leg], labelspacing=0.25)
    plt.xlabel(units['x'])
    plt.ylabel(units['z'])
    if title:
        plt.title(title)
        

def plot_diagnostic(fitter):
    residuals = fitter.residuals
    u, s, v = np.linalg.svd(residuals)
    normed_res = residuals / np.std(residuals, 0)
    plt.subplot2grid((3, 3), (0, 0), 2, 3).imshow(normed_res, vmin=-0.5,
                                             vmax=0.5, aspect='auto')
    plt.subplot2grid((3, 3), (2, 0)).plot(fitter.t, u[:,:2])
    plt.subplot2grid((3, 3), (2, 1)).plot(fitter.wl, v.T[:,:2])
    ax=plt.subplot2grid((3, 3), (2, 2))
    ax.stem(range(1, 11), s[:10])
    ax.set_xlim(0, 12)

def plot_spectra(fitter, tp=None, pol=False, num_spec=8, use_m=False,
                 cm='Spectral', lw=1.5):
    """
    Plots the transient spectra of an fitter object.
    """
    t = fitter.t
    tmin, tmax = t.min(),t.max()
    if tp is None: 
        tp = np.logspace(np.log10(0.100), np.log10(tmax), num=num_spec)
        tp = np.hstack([-0.5, -.1, 0, tp])
    tp = np.round(tp, 2)    
    t0 = fitter.last_para[fitter.model_disp]
    if use_m:
        data_used = fitter.m.T
    else:
        data_used = fitter.data
    
    if hasattr(fitter, 'tn'):
        tn = fitter.tn
        t0 = 0.
    else:
        tn = np.zeros(fitter.data.shape[1])
    specs = zero_finding.interpol(dv.tup(fitter.wl, fitter.t, data_used),
                             tn, t0, tp).data    
    
    p1 = plt.plot(fitter.wl, specs[:, :fitter.wl.size].T, lw=2*lw)    

    if cm:
        use_cmap(p1, cmap=cm) 
        
    
    if pol:
        p2 = plt.plot(fitter.wl, specs[:, fitter.wl.size:].T, lw=lw)    
        dv.equal_color(p1, p2)
    plt.legend([unicode(i)+u' '+units['y'] for i in np.round(tp,2)],
                ncol=2,  labelspacing=0.25)
    plt.axhline(0, color='grey', zorder=-10, ls='--')
    plt.autoscale(1, tight=1)
    plt.xlabel(units['x'])
    plt.ylabel(units['z'])
    if title:
        plt.title(title)


def plot_transients(fitter, wls, pol=False, plot_fit=True, scale='linear',
                    plot_res=False):
    wls = np.array(wls)
    idx = np.argmin(np.abs(wls[:,None]-fitter.wl[None,:]), 1)    
    names = [str(i) + u' ' + units['x'] for i in np.round(fitter.wl[idx])]
    
    if hasattr(fitter, 't_mat'):
        t = fitter.t_mat[:, idx]        
    else:
        t = fitter.t + fitter.last_para[0]
    
    data_to_plot =  fitter.data[:, idx]
    if plot_res: 
        data_to_plot -= fitter.model[:, idx]
    p1 = plt.plot(t, data_to_plot , '^')
    
    if pol: 
        p2 = plt.plot(t, fitter.data[:, idx + fitter.data.shape[1] / 2], 'o') 
        dv.equal_color(p1, p2)
    
    plt.legend(names, scatterpoints=1, numpoints=1)
    
    if plot_fit and hasattr(fitter,'model'):       
        plt.plot(t, fitter.model[:, idx], 'k')
        if pol:
            plt.plot(t, 
                     fitter.model[:, idx + fitter.data.shape[1] / 2], 'k')
            
    plt.autoscale(1, tight=1)
    plt.xlabel(units['y'])
    plt.ylabel(units['z'])
    if scale != 'linear':
        plt.xscale(scale)
    if title:
        plt.title(title)

def plot_residuals(fitter, wls, scale='linear'):
    wls = np.array(wls)
    idx = np.argmin(np.abs(wls[:, None] - fitter.wl[None, :]), 1)
    plt.plot(fitter.t, fitter.residuals[:, idx], '-^')
    plt.legend([unicode(i) + u' ' + units['x'] for i in np.round(fitter.wl[idx])],
                 labelspacing=0.25)
    plt.autoscale(1, tight=1)
    plt.xlabel(units['y'])
    plt.ylabel(units['z'])
    if scale != 'linear':
        plt.xscale(scale)
    if title:
        plt.title(title)
        
def a4_overview(fitter, fname, plot_fastest=1, title=None):
    plt.ioff()    
    f=plt.figure(1, figsize=(8.3, 12))
    plt.subplot(321)
    plt.pcolormesh(fitter.wl, fitter.t, fitter.data)
    plt.yscale('symlog')
    plt.autoscale(1, tight=1)
    plt.subplot(322)
    plt.imshow(fitter.residuals / fitter.residuals.std(0), aspect='auto')
    if title:    
        plt.title(title)
    plt.autoscale(1, tight=1)
    plt.subplot(323)
    plot_das(fitter, plot_fastest)
    plt.subplot(324)
    plot_das(fitter, 1, normed=True)
    plt.subplot(325)
    plot_spectra(fitter)
    plt.subplot(326)    
    wl = fitter.wl
    ind = [int(round(i)) for i in np.linspace(wl.min(), wl.max(), 10)]    
    plot_transients(fitter, ind, scale='symlog')
    plt.gcf().set_size_inches((8.2, 12))
    plt.tight_layout()
    plt.draw_if_interactive()
    f.savefig(fname, dpi=600)    
    plt.ion()
    
def _plot_zero_finding(tup, raw_tn, fit_tn, cor):
    ax1 = plt.subplot(121)
    ax1.plot(tup.wl, raw_tn)    
    ax1.plot(tup.wl, fit_tn)    
    ax1.pcolormesh(tup.wl, tup.t, tup.data)
    ax1.set_ylim(fit_tn.min(), fit_tn.max())
    ax2 = plt.subplot(122)
    ax2.pcolormesh(cor.wl, cor.t, cor.data)
    ax2.set_ylim(fit_tn.min(), fit_tn.max())
    
    
def make_legend(p, err, n):
    dig = np.floor(np.log10(err))
    l = []
    for i in range(2, n + 2):
        val = str(np.around(p[i], -int(dig[i])))
        erri = str(np.ceil(round(err[i] * 10**(-dig[i]),3)) * 10**(dig[i]))
        s = ''.join(['$\\tau_', str(int(i - 1)), '=', val, '\\pm ', erri, ' $ps'])
        l.append(s)
    return l

def use_cmap(pl, cmap='RdBu'):
    cm = plt.get_cmap(cmap)
    idx = np.linspace(0, 1, len(pl))
    for i, p in enumerate(pl):
        p.set_color(cm(idx[i]))
    

def make_legend_noerr(p, err, n):
    dig = np.floor(np.log10(err))
    l = []
    for i in range(2,n+2):
        val = str(np.around(p[i], -int(dig[i])))        
        l.append('$\\tau_' + str(int(i - 1)) + '$=' + val + ' ps')
    return l
    
    
def _plot_kin_res(x):
    import networkx as nx
    res, c, A, g = fit(x[0], 'p')
    clf()
    subplot(131)
    p1=plot(wl, c[:].T)
    #plot(wl, -c[-1].T)
    xlabel('cm-1')
    ylabel('OD')
    subplot(132)
    xlabel('t')
    ylabel('conc')
    plot(f.t, A)
    xscale('log')
    subplot(133)
    

    for i in g.nodes():
        for j in g[i]:        
            g[i][j]['tau'] = '%2d'%g.edge[i][j]['tau']
            print g[i][j]['tau']

    pos = {'S1_hot':(0, 3), 'S1_warm':(0,2.3),  'S1':(0, 1.5),
           'T_hot':(1, 1.5), 'T1':(1,1), 'S0': (0,0)}
#pos = nx.spring_layout(g, pos)
    col = [i.get_color() for i in p1]
    nx.draw(g, pos, node_size=2000, node_color=col)        
    nx.draw_networkx_edge_labels(g, pos)
    figure()
    for i in [0, 5, 10, 20, -1]:
        plot(wl, f.data[i, :],'ro')
        plot(wl, (f.data - res)[i, :],'k')
        plot(wl, res[i,:])