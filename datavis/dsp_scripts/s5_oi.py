"""
做某一个时间宽度均值下，不同行权价宽度的 OI 曲面，我叫做卷轴曲面。
Open Interest Surface Calculation
Simplified to the following steps:
1. Use a filter on time axis.
2. Intepolate on strike axis.
3. Use different gaussian sigmas alongside the spot price.
"""

import pandas as pd
import numpy as np
import scipy.signal as ssig

from s1_dsp import remove_dup_cut, smooth_time_axis, smooth_spot_df, interpolate_strike, downsample_time, calc_window
from dsp_config import DATA_DIR, get_spot_config, gen_wide_suffix

DSP_SEC = 60

def read_file(spot: str, suffix: str, wide: bool):
    df = pd.read_csv(f'{DATA_DIR}/dsp_input/strike_oi_diff_{spot}_{suffix}.csv')
    df['dt'] = pd.to_datetime(df['dt'])
    df = remove_dup_cut(df, wide=wide)
    return df

def smooth_column_time_grid(
        opt_df: pd.DataFrame, col_name: str,
        dsp_sec: int, ts_sigma_sec: int):
    """对于某一列的数据，进行时间轴的平滑处理"""
    grid_1d = smooth_time_axis(opt_df, col_name, dsp_sec, ts_sigma_sec)
    grid_1d = interpolate_strike(grid_1d)
    return grid_1d

def sliding_window_with_padding(df, winsize):
    """让每一列的元素变成左右 N 列元素的数组"""
    result = []
    pad_size = (winsize - 1) // 2
    # 这里先转置 DataFrame，然后对每一列进行填充
    df_t = df.transpose()
    for colname in df_t.columns:
        # 对原先的每一行左右进行填充
        col = df_t[colname]
        padded_row = np.pad(col.values, (pad_size, pad_size), mode='edge')
        # 滑动窗口的方式获取原先 N 列对应的数组
        result.append([padded_row[i:i+winsize] for i in range(len(col))])
    return pd.DataFrame(result, columns=df.columns, index=df.index)

def sliding_melt(df: pd.DataFrame, winsize: int, col_name: str):
    df = sliding_window_with_padding(df, winsize)
    df = df.reset_index()
    df = df.melt(id_vars='dt', var_name='strike', value_name=col_name)
    df = df.set_index('dt')
    return df

def spot_intersect(spot_df: pd.DataFrame, oi_df: pd.DataFrame):
    spot_df = spot_df.reset_index()
    spot_df['dt'] = pd.to_datetime(spot_df['dt'])
    spot_df['spot_price'] = pd.to_numeric(spot_df['spot_price'])
    spot_df = spot_df.rename(columns={'spot_price': 'price'}).sort_values(['price', 'dt'])
    spot_df = spot_df[['dt', 'price']]

    oi_df = oi_df.reset_index()
    oi_df['dt'] = pd.to_datetime(oi_df['dt'])
    oi_df['strike'] = pd.to_numeric(oi_df['strike'])
    oi_df = oi_df.rename(columns={'strike': 'price'}).sort_values(['price', 'dt'])

    merged_df = pd.merge_asof(spot_df, oi_df, on='price', by='dt', direction='nearest')
    merged_df = merged_df.set_index('dt').sort_index()
    return merged_df

def gaussian_dot_column(df: pd.DataFrame, col_name: str, winsize: int, sigma: int):
    """对于某一列的数据，进行高斯处理"""
    gau = ssig.windows.gaussian(winsize, sigma)
    gau = gau / gau.sum()
    df[col_name] = df[col_name].map(lambda x: np.dot(x, gau))
    return df

def melt_intersect_dot(spot_df: pd.DataFrame, oi_df: pd.DataFrame, col_name: str,
        dsp_sec: int, ts_sigma: int, strike_sigma: float):
    grid_1d = smooth_column_time_grid(oi_df, col_name, dsp_sec, ts_sigma)
    grid_1d.to_csv(f'{DATA_DIR}/tmp/grid_1d_{col_name}_{ts_sigma}_{strike_sigma}.csv')
    strikes = grid_1d.columns
    # print(strikes)
    win_size, sigma, med = calc_window(strikes, strike_sigma, 3.5)
    # 这一步防止过度 padding 这是 s5 和 s1 脚本最大的区别
    win_size = min(len(strikes), win_size)
    melt_df = sliding_melt(grid_1d, win_size, col_name)
    intersect_df = spot_intersect(spot_df, melt_df)
    intersect_df.to_csv(f'{DATA_DIR}/tmp/intersect_{col_name}_{ts_sigma}_{strike_sigma}.csv')
    # print(intersect_df)
    # print(win_size, sigma, med)
    intersect_df = gaussian_dot_column(intersect_df, col_name, win_size, sigma)
    return intersect_df

def cp_dot(spot_df: pd.DataFrame, oi_df: pd.DataFrame,
        dsp_sec: int, ts_sigma: int, strike_sigma: float,
        only_cp: bool):
    print(f'processing ts={ts_sigma}, strike={strike_sigma}')
    oi_df['oi_diff_cp'] = oi_df['oi_diff_c'] - oi_df['oi_diff_p']

    if only_cp:
        oi_diff_cp = melt_intersect_dot(spot_df, oi_df, 'oi_diff_cp', dsp_sec, ts_sigma, strike_sigma)
        cp = pd.concat([oi_diff_cp['oi_diff_cp']], axis=1)
        cp = cp.rename(columns={'oi_diff_cp': f'oi_cp_{ts_sigma}_{strike_sigma}'})
    else:
        oi_diff_c = melt_intersect_dot(spot_df, oi_df, 'oi_diff_c', dsp_sec, ts_sigma, strike_sigma)
        oi_diff_p = melt_intersect_dot(spot_df, oi_df, 'oi_diff_p', dsp_sec, ts_sigma, strike_sigma)
        cp = pd.concat([oi_diff_c['oi_diff_c'], oi_diff_p['oi_diff_p']], axis=1)
        cp['oi_diff_cp'] = cp['oi_diff_c'] - cp['oi_diff_p']
        cp = cp.rename(columns={
                'oi_diff_c': f'oi_c_{ts_sigma}_{strike_sigma}',
                'oi_diff_p': f'oi_p_{ts_sigma}_{strike_sigma}',
                'oi_diff_cp': f'oi_cp_{ts_sigma}_{strike_sigma}',
            })
    # print(cp)
    return cp

def cp_batch(spot_df: pd.DataFrame, oi_df: pd.DataFrame, dsp_sec: int,
        ts_sigma_list: list[int], strike_sigma_list: list[float],
        only_cp: bool):
    cp_list = []
    for ts_sigma in ts_sigma_list:
        for strike_sigma in strike_sigma_list:
            cp = cp_dot(spot_df, oi_df, dsp_sec, ts_sigma, strike_sigma, only_cp=only_cp)
            cp_list.append(cp)
    merged = pd.concat([spot_df, *cp_list], axis=1)
    return merged

def calc_intersect(spot: str, suffix: str, wide: bool):
    df = read_file(spot, suffix, wide)
    spot_config = get_spot_config(spot)
    spot_df = smooth_spot_df(df, DSP_SEC, spot_config.oi_ts_gaussian_sigmas)
    cp_df = cp_batch(spot_df, df, DSP_SEC,
            spot_config.oi_ts_gaussian_sigmas,
            spot_config.get_strike_sigmas(wide),
            only_cp=True)
    cp_df.to_csv(f'{DATA_DIR}/dsp_conv/merged_{spot}_{suffix}_s5{gen_wide_suffix(wide)}.csv')

if __name__ == '__main__':
    calc_intersect('159915', 'exp20250122_date20250108')


