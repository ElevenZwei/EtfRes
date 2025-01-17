import pandas as pd
import numpy as np

# 创建示例 DataFrame
df = pd.DataFrame({
    'a': [1, 2, 3],
    'b': [4, 5, 6],
    'c': [7, 8, 9],
    'd': [10, 11, 12]
})

# 获取 DataFrame 的列名
columns = df.columns

# 定义填充函数，填充每行的两侧并滑动窗口
def sliding_window_with_padding(df, winsize):
    result = []
    pad_size = (winsize - winsize % 2) // 2
    # 这里先转置 DataFrame，然后对每一列进行填充
    df_t = df.transpose()
    for colname in df_t.columns:
        # 对原先的每一行左右进行填充
        col = df_t[colname]
        padded_row = np.pad(col.values, (pad_size, pad_size), mode='edge')
        # 滑动窗口的方式获取原先 N 列对应的数组
        result.append([padded_row[i:i+winsize] for i in range(len(col))])
    return pd.DataFrame(result, columns=df.columns)

def strike_pivot_id_grid(strike_grid: pd.DataFrame):
    """对于一个 strike grid，生成一个编号的 pivot grid"""
    pivot_grid = pd.DataFrame(
            np.tile(np.arange(len(strike_grid.columns)), (len(strike_grid), 1)),
            columns=strike_grid.columns, index=strike_grid.index)
    return pivot_grid

# 调用函数处理 DataFrame
result = sliding_window_with_padding(df, winsize=3)

# 打印结果
print(result)
print(result.iloc[0, 3].shape)
print(strike_pivot_id_grid(result))