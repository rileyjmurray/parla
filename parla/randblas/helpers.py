from parla.randblas.enums import Layout


def to_2d_array(A_ptr, rows_A, cols_A, lda, layout):
    # This is Python-specific.
    if layout == Layout.ColMajor:
        A = A_ptr[:lda * cols_A].reshape((lda, cols_A), order='F')
        A = A[:rows_A, :]
    else:
        A = A_ptr[:lda * rows_A].reshape((rows_A, lda), order='C')
        A = A[:, :cols_A]
    return A


def indexing_bounds(A0_rows, A0_cols, vpoA, A_rows, A_cols, layout):
    # This will be needed in the C++ implementation of RandBLAS.
    #
    #   It identifies row and column index bounds to define a matrix
    #   of shape (A_rows, A_cols), assuming that matrix was formed by
    #   reading a vectorized representation of a matrix of shape
    #   (A0_rows, A0_cols) (vectorization specified by "layout"),
    #   starting at index "vpoA".
    #
    if layout == Layout.ColMajor:
        col_start = vpoA // A0_rows
        row_start = vpoA % A0_rows
    else:
        row_start = vpoA // A0_cols
        col_start = vpoA % A0_cols
    row_end = row_start + A_rows
    col_end = col_start + A_cols
    return (row_start, row_end), (col_start, col_end)


def explicit_skop_submatrix(S0_data, vpos, rows_S, cols_S, lds, layout):
    # This is Python-specific.
    if S0_data.ndim == 2:
        rows_S0, cols_S0 = S0_data.shape
        (r0, r1), (c0, c1) = indexing_bounds(rows_S0, cols_S0, vpos, rows_S, cols_S, layout)
        S = S0_data[r0:r1, c0:c1]
    elif S0_data.ndim == 1:
        S_data = S0_data[vpos:]
        S = to_2d_array(S_data, rows_S, cols_S, lds, layout)
    else:
        raise ValueError(f'S0_data.ndim must be 1 or 2, but is {S0_data.ndim}.')
    return S


def write_back(B, B_ptr, n, d, ldb, layout):
    # Write back to memory in B_ptr.
    #   This is mind-bogglingly slow.
    #   This won't be needed in RandBLAS.
    #   It's needed here in case B doesn't share the same
    #       memory as B_ptr.
    if layout == Layout.ColMajor:
        for col in range(n):
            start = ldb * col
            stop = start + d
            B_ptr[start:stop] = B[:, col]
    else:
        for row in range(d):
            start = ldb * row
            stop = start + n
            B_ptr[start:stop] = B[row, :]
    pass

