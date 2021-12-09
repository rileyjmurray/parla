import numpy as np
import scipy.linalg as la
from scipy.sparse.linalg import LinearOperator
from parla.comps.interpolative import RowOrColSelection, ROCS1
from parla.comps.sketchers.aware import RowSketcher, RS1
import parla.comps.sketchers.oblivious as osk
import parla.comps.interpolative as id_comps
import parla.utils.linalg_wrappers as ulaw


class OneSidedID:
    """One-sided ID (row or column)"""

    def __call__(self, A, k, over, axis, gen):
        """
        Run a rank-k RowID (axis=0) or ColumnID (axis=1) on A,
        using oversampling parameter over.

        A RowID consists of a matrix "Z" and a length-k index vector "Is" so
        that A \approx Z @ A[Is,:]. The rows of Z must contain a
        possibly-permuted k-by-k identity matrix, such that

            A[Is, :] = (Z @ A[Is, :])[Is,:].

        Note that if we assume the rows of A[Is, :] are linearly independent, then
        the above equations are equivalent to Z[Is, :] being a k-by-k identity matrix.

        A ColumnID consists of a matrix "X" and a length-k index vector "Js" so
        that A \approx A[:,Js] @ X. The columns of X must contain a
        possibly-permuted k-by-k identity matrix, such that

            A[:, Js] = (A[:,Js] @ X)[:, Js].

        As with row ID, this means X[:, Js] is a k-by-k identity matrix
        """
        raise NotImplementedError()


#NOTE: Could merge with osid2 by adding a single additional keyword argument
def osid1(A, k, over, p, axis, rng):
    rng = np.random.default_rng(rng)
    skop = osk.SkOpGA()
    rs = RS1(skop, p - 1, ulaw.orth, passes_per_stab=1)
    alg = OSID1(rs)
    res = alg(A, k, over, axis, rng)
    return res


class OSID1(OneSidedID):
    """
    Sketch + QRCP approach to ID

    See Voronin & Martinsson, 2016, Section 5.1.
    """

    def __init__(self, sk_op: RowSketcher):
        self.sk_op = sk_op

    def __call__(self, A, k, over, axis, rng):
        rng = np.random.default_rng(rng)
        if axis == 0:
            # Row ID
            Sk = self.sk_op(A, k + over, rng)
            Y = A @ Sk
            X, Is = id_comps.qrcp_osid(Y, k, axis=0)
            return X, Is
        elif axis == 1:
            # Column ID
            Sk = self.sk_op(A.T, k + over, rng).T
            Y = Sk @ A
            Z, Js = id_comps.qrcp_osid(Y, k, axis=1)
            return Z, Js
        else:
            raise ValueError()


def osid2(A, k, over, p, axis, rng):
    rng = np.random.default_rng(rng)
    skop = osk.SkOpGA()
    rs = RS1(skop, p - 1, ulaw.orth, passes_per_stab=1)
    alg = OSID2(rs)
    res = alg(A, k, over, axis, rng)
    return res


class OSID2(OneSidedID):
    """
    Sketch + (QRCP skeleton) + (least squares) approach to ID

    See Dong & Martinsson, 2021.
    """

    def __init__(self, sk_op: RowSketcher):
        self.sk_op = sk_op

    def __call__(self, A, k, over, axis, rng):
        rng = np.random.default_rng(rng)
        if axis == 0:
            # Row ID
            Sk = self.sk_op(A, k + over, rng)
            Y = A @ Sk
            _, _, Is = la.qr(Y.T, mode='economic', pivoting=True)
            Is = Is[:k]
            X = ulaw.apply_pinv_on_right(A, operator=A[Is, :])
            return X, Is
        elif axis == 1:
            # Column ID
            Sk = self.sk_op(A.T, k + over, rng).T
            Y = Sk @ A
            _, _, J = la.qr(Y, mode='economic', pivoting=True)
            Js = J[:k]
            Z = ulaw.apply_pinv_on_left(A, operator=A[:, Js])
            return Z, Js
        else:
            raise ValueError()


class TwoSidedID:
    """Fixed rank Double ID"""

    def __call__(self, A, k, over, rng):
        """
        Return (Z, Is, X, Js) where
            Z is A.shape[0]-by-k,
            Is is an index vector of length k,
            X is k-by-A.shape[1],
            Js is an index vector of length k,
        so that
            A \approx Z @ A[Is, Js] @ X.

        Use oversampling parameter "over" in the sketching step.
        """
        raise NotImplementedError()


def tsid1(A, k, over, p, rng):
    rng = np.random.default_rng(rng)
    skop = osk.SkOpGA()
    rs = RS1(skop, p - 1, ulaw.orth, passes_per_stab=1)
    osid = OSID1(rs)
    tsid = TSID1(osid)
    Z, Is, X, Js = tsid(A, k, over, rng)
    return Z, Is, X, Js


class TSID1(TwoSidedID):
    """
    Obtain a one-sided ID by any means, then deterministically extend
    to a two-sided ID.

    Using OSID1 would make this a "Sketch + QRCP" approach to double ID,
    as described in Voronin & Martinsson, 2016, Sections 2.4 and 4.
    """

    def __init__(self, osid: OneSidedID):
        self.osid = osid

    def __call__(self, A, k, over, rng):
        rng = np.random.default_rng(rng)
        if A.shape[0] > A.shape[1]:
            X, Js = self.osid(A, k, over, axis=1, rng=rng)
            Z, Is = id_comps.qrcp_osid(A[:, Js], k, axis=0)
        else:
            Z, Is = self.osid(A, k, over, axis=0, rng=rng)
            X, Js = id_comps.qrcp_osid(A[Is, :], k, axis=1)
        return Z, Is, X, Js


class CURDecomposition:
    """Fixed rank CUR Decomposition"""

    def __call__(self, A, k, over, rng):
        """
        Return (J, U, I) where
            C = A[:, J] has k columns,
            R = A[I, :] has k rows,
            U is an ndarray or LinearOperator
        so that
            A \approx C @ U @ R.

        Use oversampling parameter "over" in the sketching step.
        """
        raise NotImplementedError()


def cur1(A, k, over, p, rng):
    rng = np.random.default_rng(rng)
    skop = osk.SkOpGA()
    rs = RS1(skop, p - 2, ulaw.orth, passes_per_stab=1)
    osid = OSID1(rs)
    cur = CUR1(osid)
    Js, U, Is = cur(A, k, over, rng)
    return Js, U, Is


class CUR1(CURDecomposition):

    def __init__(self, osid: OneSidedID):
        self.osid = osid

    def __call__(self, A, k, over, rng):
        rng = np.random.default_rng(rng)
        if A.shape[0] > A.shape[1]:
            X, Js = self.osid(A, k, over, axis=1, rng=rng)
            # A \approx A[:, Js] @ X
            _, _, Is = la.qr(A[:, Js].T, mode='economic', pivoting=True)
            Is = Is[:k]
            U = ulaw.apply_pinv_on_right(X, operator=A[Is, :])
            # U = X (A[Is, :]^\dagger)
            return Js, U, Is
        else:
            Z, Is = self.osid(A, k, over, axis=0, rng=rng)
            # A \approx Z @ A[Is, :]
            _, _, Js = la.qr(A[Is, :], mode='economic', pivoting=True)
            Js = Js[:k]
            U = ulaw.apply_pinv_on_left(Z, operator=A[:, Js])
            # U = A[:, Js]^\dagger Z
            return Js, U, Is
