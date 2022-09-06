import warnings

import numpy as np
import scipy.linalg as la
from scipy.sparse import linalg as sparla

from parla.comps.determiter.lsqr import lsqr
from parla.comps.determiter.pcg import pcg
from parla.comps.preconditioning import a_lift_precond


def pcss1(A, b, c, delta, tol, iter_lim, R, upper_tri, z0):
    """Instantiates and calls a PcSS1 PrecondSaddleSolver algorithm."""
    alg = PcSS1()
    return alg(A, b, c, delta, tol, iter_lim, R, upper_tri, z0)


def pcss2(A, b, c, delta, tol, iter_lim, R, upper_tri, z0):
    """Instantiates and calls a PcSS2 PrecondSaddleSolver algorithm."""
    alg = PcSS2()
    return alg(A, b, c, delta, tol, iter_lim, R, upper_tri, z0)


class PrecondSaddleSolver:

    def __call__(self, A, b, c, delta, tol, iter_lim, R, upper_tri, z0):
        """
        The problem data (A, b, c, delta) define a block linear system

             [  I   |     A   ] [y_opt] = [b]           (*)
             [  A'  | -delta*I] [x_opt]   [c].

        The matrix A is m-by-n and tall, b and c are vectors, and delta is >= 0.
        This method produces (x_approx, y_approx) that approximate (x_opt, y_opt).

        This method uses some iterative algorithm with tol and iter_lim as
        termination criteria. The meaning of tol is implementation-dependent.

        The underlying iterative algorithm uses R as a preconditioner and
        initializes x_approx based on the pair (R, z0).

            If upper_tri is True, then we expect that the condition number of
            A_{pc} := (A R^{-1}) isn't large, and we initialize x_approx = R^{-1} z0.

            If upper_tri is False, then we expect that the condition number of
            A_{pc} := (A R) is not large and we initialize x_approx = R z0.

        Parameters
        ----------
        A : ndarray
            Data matrix with m rows and n columns.
        b : ndarray
            Upper block in the right-hand-side. b.shape = (m,).
        c : ndarray
            The lower block the right-hand-side. c.shape = (n,).
        delta : float
            Nonnegative regularization parameter.
        tol : float
            Used as stopping criteria.
        iter_lim : int
            An upper-bound on the number of steps the iterative algorithm
            is allowed to take.
        R : ndarray
            Defines the preconditioner, has R.shape = (n, n).
        upper_tri : bool
            If upper_tri is True, then precondition by M = R^{-1}.
            If upper_tri is False, then precondition by M = R.
        z0 : Union[None, ndarray]
            If provided, use as an initial approximate solution to (Ap'Ap) x = Ap' b,
            where Ap = A M is the preconditioned version of A.

        Returns
        -------
        x_approx : ndarray
            Has size (n,).
        y_approx : ndarray
            Has size (m,). Usually set to y := b - A x_approx, which solves the
            upper block of equations in (*).
        errors : ndarray
            errors[i] is some error metric of (x_approx, y_approx) at iteration i
            of the algorithm. The algorithm took errors.size steps.

        Notes
        -----
        The following characterization holds for x_opt in (*):
            (A' A + delta * I) x_opt = A'b - c.
        We call that system the "normal equations".
        """
        raise NotImplementedError()


class PcSS1(PrecondSaddleSolver):

    ERROR_METRIC_INFO = """
        2-norm of the residual from the preconditioned normal equations
    """

    def __call__(self, A, b, c, delta, tol, iter_lim, R, upper_tri, z0):
        m, n = A.shape
        if b is None:
            b = np.zeros(m)
        k = 1 if b.ndim == 1 else b.shape[1]
        if k != 1:
            raise NotImplementedError()

        if upper_tri:
            raise NotImplementedError()
        # inefficiently recover the orthogonal columns of M
        work2 = np.zeros(m)
        pc_dim = R.shape[1]
        work1 = np.zeros(pc_dim)

        if delta > 0:
            sing_vals = 1 / la.norm(R, axis=0)
            V = R * sing_vals
            # Update sing_vals = sqrt(sing_vals**2 + delta).
            #   (The method below isn't a stable way of doing that.)
            sing_vals **= 2
            sing_vals += delta
            sing_vals **= 0.5
            R[:] = V[:]
            R /= (sing_vals/sing_vals[-1])
            work3 = np.zeros(n)

        fullrank_precond = pc_dim == n

        def mv_pre(vec):
            # The preconditioner is RR' + (I - VV')
            np.dot(R.T, vec, out=work1)
            res = np.dot(R, work1)
            if not fullrank_precond:
                res += vec
                np.dot(V.T, vec, out=work1)
                np.dot(V, work1, out=work3)
                res -= work3
            return res

        def mv_gram(vec):
            np.dot(A, vec, out=work2)
            res = A.T @ work2
            res += delta * vec
            return res

        rhs = A.T @ b
        if c is not None:
            rhs -= c

        if z0 is None or (not fullrank_precond):
            # TODO: proper initialization with low-rank preconditioners
            x = np.zeros(n)
        else:
            x = R @ z0

        x, residuals = pcg(mv_gram, rhs, mv_pre, iter_lim, tol, x)

        y = b - A @ x
        result = (x, y, residuals)

        return result


class PcSS2(PrecondSaddleSolver):

    ERROR_METRIC_INFO = """
        2-norm of the residual from the preconditioned normal equations
    """

    def __init__(self, orig_xnorm=True, allow_consistent_term=False):
        self.orig_xnorm = orig_xnorm
        self.allow_consistent_term = allow_consistent_term

    def __call__(self, A, b, c, delta, tol, iter_lim, R, upper_tri, z0):
        m, n = A.shape
        k = 1 if (b is None or b.ndim == 1) else b.shape[1]

        A_pc, M_fwd, M_adj = a_lift_precond(A, delta, R, upper_tri, k)

        if c is None or la.norm(c) == 0:
            # Overdetermined least squares
            if delta > 0:
                b = np.concatenate((b, np.zeros(n)))
            result = lsqr(A_pc, b, atol=tol, btol=tol, iter_lim=iter_lim, x0=z0,
                          orig_xnorm=self.orig_xnorm, allow_consistent_term=self.allow_consistent_term)
            x = M_fwd(result[0])
            y = b[:m] - A @ x
            result = (x, y, result[7], result[1])
            return result

        elif b is None or la.norm(b) == 0:
            # Underdetermined least squares
            c_pc = M_adj(c)
            result = lsqr(A_pc.T, c_pc, atol=tol, btol=tol, iter_lim=iter_lim,
                          orig_xnorm=self.orig_xnorm)
            y = result[0]
            if delta > 0:
                y = y[:m]
                x = (A.T @ y - c) / delta
            else:
                x = np.NaN * np.empty(n)
            result = (x, y, result[7], result[1])
            return result

        else:
            raise ValueError('One of "b" or "c" must be zero.')


class PcSS3(PrecondSaddleSolver):
    """Use a no-refresh Newton-sketch style iterative refinement scheme."""

    ERROR_METRIC_INFO = PcSS2.ERROR_METRIC_INFO

    MIN_TOL = 10*np.finfo(float).eps

    def __init__(self, allow_consistent_term=False):
        self.allow_consistent_term = allow_consistent_term

    def __call__(self, A, b, c, delta, tol, iter_lim, R, upper_tri, z0):

        m, n = A.shape
        assert m == b.shape[0]
        assert b.ndim == 1
        if c is not None:
            raise NotImplementedError()
        if delta > 0:
            raise NotImplementedError()
        if upper_tri:
            raise NotImplementedError()
        else:
            M = R

        if tol < self.MIN_TOL:
            msg = f"\nThe provided tolerance of {tol} is too small;" \
                  f"\nwe're changing it to the smallest-admissible" \
                  f"\ntolerance: {self.MIN_TOL}."
            warnings.warn(msg)
            tol = self.MIN_TOL
        max_iter = 5*n
        if iter_lim > max_iter:
            msg = f"\nThe provided iteration limit {iter_lim} is too large;" \
                  f"\nwe're changing it to the largest allowable iteration" \
                  f"\nlimit, which is 5*n={max_iter}."
            warnings.warn(msg)
            iter_lim = max_iter

        # (A'A + \delta I) x = A'b - c
        #  A_pc = [A; \sqrt{\delta}] M,
        #       where the columns of (S A M) form an orthonormal
        #       basis for the range of (S A), and where S was some
        #       sketching operator.
        # Algebra shows that ...
        #
        #   (A_sk' A_sk)^{-1} = M M'.
        #
        # Initialization:
        #       (0a) x = M z0.
        #       (0b) r = A'b - c - A'A x - \delta x
        #
        # Iterate by computing
        #       (2) dx  = M M' r
        #       (3) x  += dx
        #       (1) rhs = A'b - c - A'A x - \delta x
        #               Equivalently,  rhs -= (A'A dx - delta * dx)
        #
        # Termination criteria. We mimick SciPy LSQR w/ preconditioned A.
        #         metric1 = ||y || / (||b|| + scale*||z||)
        #             LSQR tests that ||y|| / ||b|| <= (TOL_B + TOL_A*scale*||z||/||b||)
        #             we set TOL_A = TOL_B.
        #         metric2 = ||M'A' y|| / (scale * ||y||)
        #     where scale = sqrt(n), y = b - Ax, and x = M z.
        #
        #    This is equivalent to how we call LSQR, except that LSQR maintains
        #    a sequence of non-decreasing values for "scale" that converge to
        #    ||A M||_F. We terminate once min(metric1, metric2) falls below "tol".

        # workspace and error with x=0
        #       errors = absolute preconditioned normal equation error.
        errors = -np.ones(iter_lim + 2)
        rank = M.shape[1]
        z = np.zeros(rank)
        dz = np.zeros(rank)
        x = np.zeros(n)
        dx = np.zeros(n)
        y = b.copy()
        rhs = A.T @ b
        drhs = np.zeros(n)
        work_ax1 = np.zeros(m)
        work_ax2 = np.zeros(m)
        nrm_b = la.norm(b)
        sqrt_n = n**0.5

        def step_size(dx_, work_ax1_, work_ax2_):
            # Adx = A @ dx_
            # num = Adx @ (b - A @ x)
            # den = Adx @ Adx
            np.dot(A, dx_, out=work_ax1_)
            den = np.linalg.norm(work_ax1_)
            work_ax1_ /= den
            np.dot(A, x, out=work_ax2_)
            work_ax2_ -= b  # work_ax2_ = Ax - b
            neg_num = work_ax1_ @ work_ax2_
            if den > 0:
                return -neg_num / den
            nrm_dx = la.norm(dx_)
            if nrm_dx > 0:
                alpha_ = x @ dx_ / (nrm_dx ** 2)
                return alpha_
            return np.NaN

        # Initialize
        if z0 is not None and la.norm(z0) > 0:
            dz = z0[:]  # dz0
            np.dot(M, dz, out=dx)  # dx0
            alpha = step_size(dx, work_ax1, work_ax2)
            dx *= alpha  # dx
            x[:] = dx  # x = dx
            np.dot(A, dx, out=work_ax1)  # -dy
            y -= work_ax1
            z[:] = alpha * dz  # z = dz = alpha * dz0
            np.dot(A.T, work_ax1, out=drhs)
            rhs -= drhs

        # Check stopping criteria; re-use dz later on.
        np.dot(M.T, rhs, out=dz)
        err = la.norm(dz)
        errors[0] = err
        nrm_y = la.norm(y)
        metric1 = nrm_y / (nrm_b + sqrt_n * la.norm(z))
        metric2 = err / (sqrt_n * nrm_y)
        if self.allow_consistent_term:
            error_func = lambda _metric1, _metric2: min(_metric1, _metric2)
        else:
            error_func = lambda _metric1, _metric2: _metric2

        # main loop; start by computing dx, end by computing error
        it = 1
        iter_lim += 1
        while it < iter_lim and error_func(metric1, metric2) > tol:
            """
            Invariants:
                rhs = A'b - (A'A + delta*I) x
                dz0 = M' rhs
                dx0 = M dz0 = MM' rhs
                alpha = step_size()
                [dz, dx] = alpha*[dz0, dx0]
                dy = -A dx
                z += dz
                x += dx
                y += dy  
            """
            np.dot(M, dz, out=dx)  # dx = M M' rhs
            alpha = step_size(dx, work_ax1, work_ax2)
            if np.isnan(alpha) or alpha == 0:
                errors[it] = err
                break
            dx *= alpha
            dz *= alpha
            x += dx
            z += dz
            np.dot(A, dx, out=work_ax1)
            y -= work_ax1
            np.dot(A.T, work_ax1, out=drhs)
            if it % 50 == 0:
                np.dot(A, x, out=work_ax1)
                work_ax1 -= b
                work_ax1 *= -1
                np.dot(A.T, work_ax1, out=rhs)
            else:
                rhs -= drhs  # rhs -= alpha * (A'A dx + \delta dx)
            np.dot(M.T, rhs, out=dz)
            err = la.norm(dz)
            errors[it] = err
            it += 1
            nrm_y = la.norm(y)
            metric1 = nrm_y / (nrm_b + sqrt_n * la.norm(z))
            metric2 = err / (sqrt_n * nrm_y)
        errors = errors[errors > -1]

        if self.allow_consistent_term and metric1 <= tol:
            code = 1
        elif metric2 <= tol:
            code = 2
        else:
            code = 7

        y = b - A @ x
        return x, y, errors, code
