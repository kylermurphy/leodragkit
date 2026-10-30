"""Independent checks of the Sentman plate: closed forms from the literature, then tests.

The reference formulas at the top are written from the papers, not from leodragkit, so agreement with
them checks the Sentman code against independent derivations: Bird's sphere, Dey et al.'s DRIA plate
and sphere, and Cook's hyperthermal formula. They are test references only; analytic components are
not part of the package. Step plan and reading list: ``docs/plans/A2_independent_checks.md``.

Run: ``pytest tests/aero/test_sentman_independent_checks.py``
"""

import numpy as np
import pytest
from scipy.integrate import quad  # noqa: F401  (used once the reference formulas are written; then remove)
from scipy.special import erf, erfc  # noqa: F401  (as above)

from leodragkit.aero.gas_surface_sentman import (
    COOK_REFLECTED_SPEED_CONSTANT,
    KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
    compute_reflected_speed_ratio,
    compute_sentman_flat_plate_coefficients,
)

# --- Reference formulas, written from the papers ------------------------------------------------
#
# Sources:
# - Parham, J., & Barba, L. A. (2014). Finding the Force: Consistent Particle Seeding for Satellite
#   Aerodynamics. AIAA Modeling and Simulation Technologies Conference. doi:10.2514/6.2014-1492
#   (read as arXiv:1312.3691; eq. 4).
# - Dey, S., Anderson, P., Bukowski, A., & Pilinski, M. (2025). Investigation of gas-surface
#   interactions and neutral atmospheric properties and their impact on satellite drag coefficients.
#   Earth and Space Science, 12, e2024EA003998. doi:10.1029/2024EA003998 (eqs. 2.3–2.5).
# - Sinpetru, L. A., et al. (2022). ADBSat: Methodology of a novel panel method tool for aerodynamic
#   analysis of satellites. Computer Physics Communications, 275, 108326. doi:10.1016/j.cpc.2022.108326
#   (preprint arXiv:2104.05543v2, eq. 18; printed with a bracket typo, intended α(T_w/T_i − 1)).


def bird_sphere_drag(speed_ratio, wall_speed_ratio):
    """Drag coefficient of a fully accommodated sphere, referenced to its cross-section πR².

    Parham & Barba (2014), eq. 4, after Bird:

        C_D = exp(−S²) / (sqrt(π) S³) · (1 + 2S²) + (4S⁴ + 4S² − 1) / (2S⁴) · erf(S) + 2 sqrt(π) / (3 S_W)

    S is the speed ratio of the oncoming gas; S_W is the speed ratio at the wall temperature,
    S_W = S · sqrt(T∞ / T_w).
    """
    # 1. The two terms from the oncoming gas (the exponential and the erf term).
    s = speed_ratio
    sw = wall_speed_ratio
    exp_s = np.exp(-s**2)
    erf_s = erf(s)
    inc_t = exp_s/(np.sqrt(np.pi)*s**3)*(1+2*s**2) + (4*s**4 + 4*s**2 -1)/(2*s**4)*erf_s
    # 2. The re-emission term (last term), from the wall speed ratio, 2√π / (3 S_W).
    reem_t = 2*np.sqrt(np.pi)/(3*sw)

    return inc_t + reem_t


def dey_reflected_kinetic_temperature_kelvin(
    speed_ratio, energy_accommodation, ambient_temperature_kelvin, wall_temperature_kelvin
):
    """Kinetic temperature of the re-emitted molecules, T_k,r (Dey et al. 2025, eq. 2.4).

        T_k,r = T_k,i (1 − α) + T_s α,    with    T_k,i = m v² / (3 k_B) = (2/3) s² T∞

    The second form uses s² = m v² / (2 k_B T∞) (Dey et al., eq. 2.1). T_s is the wall temperature.
    """
    # 1. Incident kinetic temperature T_k,i from the speed ratio.
    t_ki = (2.0/3.0) * speed_ratio**2 * ambient_temperature_kelvin
    # 2. Blend it with the wall temperature by α.
    t_kr = t_ki * (1-energy_accommodation) + wall_temperature_kelvin * energy_accommodation

    return t_kr

def dey_dria_plate_drag(
    cos_incidence_angle, speed_ratio, reflected_kinetic_temperature_kelvin, ambient_temperature_kelvin
):
    """Drag coefficient of one flat surface, one side exposed, referenced to its own area (A/A_ref = 1).

    Dey et al. (2025), eq. 2.3, with γ = cos β the cosine between the surface normal and the velocity:

        C_D = γ (1 + 1/(2s²)) (1 + erf(γs)) + exp(−γ²s²) / (s sqrt(π))
              + (γ / (2s)) sqrt(T_k,r / T∞) · (γ sqrt(π) (1 + erf(γs)) + exp(−γ²s²) / s)

    Write 1 + erf(γs) as erfc(−γs): the same quantity, without the loss of digits on back faces.
    """
    # 1. The shared terms: exp(−γ²s²) and 1 + erf(γs), the latter as erfc(−γs).
    exp_t = np.exp(-cos_incidence_angle**2 * speed_ratio**2)
    erf_t = erfc(-cos_incidence_angle * speed_ratio)
    # 2. The incoming-gas terms.
    inc_t = cos_incidence_angle * (1 + 1/(2*speed_ratio**2)) * erf_t + exp_t / (speed_ratio * np.sqrt(np.pi))
    # 3. The re-emission term, from sqrt(T_k,r / T∞).
    t_kr = reflected_kinetic_temperature_kelvin
    t_inf = ambient_temperature_kelvin
    reem_t = (cos_incidence_angle / (2 * speed_ratio)) * np.sqrt(t_kr/t_inf) * \
        (cos_incidence_angle * np.sqrt(np.pi) * erf_t + exp_t / speed_ratio)

    return inc_t + reem_t


def dey_dria_sphere_drag(speed_ratio, reflected_kinetic_temperature_kelvin, ambient_temperature_kelvin):
    """Drag coefficient of a sphere, referenced to its cross-section (Dey et al. 2025, eq. 2.5).

        C_D = (2s² + 1) / (sqrt(π) s³) · exp(−s²) + (4s⁴ + 4s² − 1) / (2s⁴) · erf(s)
              + (2 sqrt(π) / (3s)) · sqrt(T_k,r / T∞)

    At full accommodation, T_k,r = T_w and this is Bird's formula.
    """
    s = speed_ratio
    t_kr = reflected_kinetic_temperature_kelvin
    t_inf = ambient_temperature_kelvin
    # 1. The incoming-gas terms (the same as Bird's).
    inc_t = (2*s**2+1)/(np.sqrt(np.pi)*s**3)*np.exp(-s**2) + (4*s**4+4*s**2-1)/(2*s**4)*erf(s)
    # 2. The re-emission term, from sqrt(T_k,r / T∞).
    reem_t = 2*np.sqrt(np.pi)/(3*s) * np.sqrt(t_kr/t_inf)

    return inc_t + reem_t


def cook_hyperthermal_drag(
    cos_incidence_angle, energy_accommodation, wall_temperature_kelvin, incident_kinetic_temperature_kelvin
):
    """Cook's hyperthermal drag coefficient of one flat plate (Sinpetru et al. 2022, eq. 18, as intended).

        C_d = 2 cos δ (1 + (2/3) cos δ sqrt(1 + α (T_w / T_i − 1)))

    T_i is the incident kinetic temperature, m V² / (3 k_B). The preprint prints the bracket as
    α T_w / (T_inf − 1); ADBSat's code uses the form above, with T_i = V² / (3R).
    """
    cos_delta = cos_incidence_angle
    alpha = energy_accommodation
    t_inc = incident_kinetic_temperature_kelvin
    t_w = wall_temperature_kelvin
    # 1. The re-emission factor sqrt(1 + α (T_w / T_i − 1)).
    reem_f = (2./3.)*cos_delta*np.sqrt(1+alpha*(t_w/t_inc -1))
    # 2. The drag coefficient.
    return 2*cos_delta*(1 + reem_f)


def integrate_plate_over_sphere(plate_drag_of_cos):
    """Sphere drag coefficient from a plate drag formula, referenced to the cross-section πR².

    A sphere element at polar angle θ from the flow has cos δ = cos θ and area 2πR² sin θ dθ, so

        C_D = (1 / πR²) ∫ c_d(cos θ) 2πR² sin θ dθ = 2 ∫₋₁¹ c_d(c) dc.

    ``plate_drag_of_cos`` is a function of one float, cos δ, returning the plate drag coefficient.
    """
    # 1. Integrate c_d(c) over c from −1 to 1 with scipy.integrate.quad (tight tolerances).
    integral, error = quad(plate_drag_of_cos, -1, 1, epsabs=1e-12, epsrel=1e-12)
    # 2. Multiply by 2.
    return 2 * integral
    


# --- Shared test conditions and helpers ---------------------------------------------------------

SPHERE_AMBIENT_TEMPERATURE_KELVIN = 922.0  # the primer's sphere cases
PLATE_AMBIENT_TEMPERATURE_KELVIN = 1000.0  # the primer's plate cases
WALL_TEMPERATURE_KELVIN = 300.0
BOTH_CONSTANTS = [KOPPENWALLNER_REFLECTED_SPEED_CONSTANT, COOK_REFLECTED_SPEED_CONSTANT]


def sentman_plate_drag(cos_incidence_angle, speed_ratio, energy_accommodation, ambient_temperature_kelvin, k):
    """Drag coefficient from the code under test, for one plate."""
    reflected = compute_reflected_speed_ratio(
        speed_ratio, ambient_temperature_kelvin, WALL_TEMPERATURE_KELVIN, energy_accommodation, k
    )
    return compute_sentman_flat_plate_coefficients(
        cos_incidence_angle, speed_ratio, reflected
    ).drag_coefficient


def sentman_sphere_drag(speed_ratio, energy_accommodation, ambient_temperature_kelvin, k):
    """Sphere drag from the code under test, by integrating its plate over a sphere."""
    return integrate_plate_over_sphere(
        lambda c: float(
            sentman_plate_drag(c, speed_ratio, energy_accommodation, ambient_temperature_kelvin, k)
        )
    )


# --- 1. Sphere at full accommodation: Bird ------------------------------------------------------


@pytest.mark.parametrize("k", BOTH_CONSTANTS)
@pytest.mark.parametrize("speed_ratio", [0.5, 1.0, 2.0, 5.0, 7.5, 10.0])
def test_sphere_at_full_accommodation_matches_bird(speed_ratio, k):
    wall_speed_ratio = speed_ratio * np.sqrt(SPHERE_AMBIENT_TEMPERATURE_KELVIN / WALL_TEMPERATURE_KELVIN)
    expected = bird_sphere_drag(speed_ratio, wall_speed_ratio)
    assert sentman_sphere_drag(speed_ratio, 1.0, SPHERE_AMBIENT_TEMPERATURE_KELVIN, k) == pytest.approx(
        expected, rel=1e-10
    )


@pytest.mark.parametrize(("speed_ratio", "primer_value"), [(5.0, 2.2140), (7.5, 2.1253), (10.0, 2.0874)])
def test_bird_reproduces_the_primers_sphere_values(speed_ratio, primer_value):
    wall_speed_ratio = speed_ratio * np.sqrt(SPHERE_AMBIENT_TEMPERATURE_KELVIN / WALL_TEMPERATURE_KELVIN)
    assert bird_sphere_drag(speed_ratio, wall_speed_ratio) == pytest.approx(primer_value, abs=5e-5)


# --- 2. Sphere at partial accommodation: Dey eq. 2.5 --------------------------------------------


@pytest.mark.parametrize("energy_accommodation", [0.0, 0.5, 0.9])
@pytest.mark.parametrize("speed_ratio", [1.0, 5.0])
def test_sphere_with_k_two_thirds_matches_dey(speed_ratio, energy_accommodation):
    reflected_kelvin = dey_reflected_kinetic_temperature_kelvin(
        speed_ratio, energy_accommodation, SPHERE_AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN
    )
    expected = dey_dria_sphere_drag(speed_ratio, reflected_kelvin, SPHERE_AMBIENT_TEMPERATURE_KELVIN)
    actual = sentman_sphere_drag(
        speed_ratio, energy_accommodation, SPHERE_AMBIENT_TEMPERATURE_KELVIN, COOK_REFLECTED_SPEED_CONSTANT
    )
    assert actual == pytest.approx(expected, rel=1e-10)


@pytest.mark.parametrize("energy_accommodation", [0.0, 0.5, 0.9])
@pytest.mark.parametrize("speed_ratio", [1.0, 5.0])
def test_sphere_with_k_one_half_matches_dey_written_with_the_reflected_speed_ratio(
    speed_ratio, energy_accommodation
):
    # Dey's re-emission term uses sqrt(T_k,r / T∞), which equals s·r for either constant (R-02 identity);
    # with k = 1/2 the reflected temperature is therefore T∞ (s r)².
    reflected = compute_reflected_speed_ratio(
        speed_ratio,
        SPHERE_AMBIENT_TEMPERATURE_KELVIN,
        WALL_TEMPERATURE_KELVIN,
        energy_accommodation,
        KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
    )
    reflected_kelvin = SPHERE_AMBIENT_TEMPERATURE_KELVIN * (speed_ratio * reflected) ** 2
    expected = dey_dria_sphere_drag(speed_ratio, reflected_kelvin, SPHERE_AMBIENT_TEMPERATURE_KELVIN)
    actual = sentman_sphere_drag(
        speed_ratio,
        energy_accommodation,
        SPHERE_AMBIENT_TEMPERATURE_KELVIN,
        KOPPENWALLNER_REFLECTED_SPEED_CONSTANT,
    )
    assert actual == pytest.approx(expected, rel=1e-10)


# --- 3. Plate: Dey eq. 2.3 ----------------------------------------------------------------------


@pytest.mark.parametrize("energy_accommodation", [0.0, 0.5, 1.0])
@pytest.mark.parametrize("speed_ratio", [0.5, 2.0, 7.0, 20.0])
def test_plate_with_k_two_thirds_matches_dey(speed_ratio, energy_accommodation):
    cos_incidence_angle = np.linspace(-1.0, 1.0, 21)
    reflected_kelvin = dey_reflected_kinetic_temperature_kelvin(
        speed_ratio, energy_accommodation, PLATE_AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN
    )
    expected = dey_dria_plate_drag(
        cos_incidence_angle, speed_ratio, reflected_kelvin, PLATE_AMBIENT_TEMPERATURE_KELVIN
    )
    actual = sentman_plate_drag(
        cos_incidence_angle,
        speed_ratio,
        energy_accommodation,
        PLATE_AMBIENT_TEMPERATURE_KELVIN,
        COOK_REFLECTED_SPEED_CONSTANT,
    )
    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-15)


# --- 4. The primer's head-on plate values -------------------------------------------------------


@pytest.mark.parametrize(
    ("energy_accommodation", "primer_value"),
    [(1.0, 2.1591), (0.9, 2.4966), (0.0, 3.4676)],
)
def test_dey_reproduces_the_primers_head_on_values_and_the_code_agrees(energy_accommodation, primer_value):
    speed_ratio = 7.0
    reflected_kelvin = dey_reflected_kinetic_temperature_kelvin(
        speed_ratio, energy_accommodation, PLATE_AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN
    )
    independent = dey_dria_plate_drag(1.0, speed_ratio, reflected_kelvin, PLATE_AMBIENT_TEMPERATURE_KELVIN)
    assert independent == pytest.approx(primer_value, abs=5e-5)
    code = sentman_plate_drag(
        1.0,
        speed_ratio,
        energy_accommodation,
        PLATE_AMBIENT_TEMPERATURE_KELVIN,
        COOK_REFLECTED_SPEED_CONSTANT,
    )
    assert code == pytest.approx(independent, rel=1e-12)


# --- 5. Hyperthermal limit, and how it differs from Cook ----------------------------------------

HYPERTHERMAL_SPEED_RATIO = 1e4
COS_INCIDENCE_ANGLES = np.array([1.0, 0.5, 0.2])


@pytest.mark.parametrize("k", BOTH_CONSTANTS)
def test_at_large_speed_ratio_sentman_drag_tends_to_its_hyperthermal_limit(k):
    # Large s: C_p → 2c² + sqrt(π) r c and C_τ → 2 sin δ c, so C_d → 2c + sqrt(π) r c².
    reflected = compute_reflected_speed_ratio(
        HYPERTHERMAL_SPEED_RATIO, PLATE_AMBIENT_TEMPERATURE_KELVIN, WALL_TEMPERATURE_KELVIN, 0.9, k
    )
    drag = compute_sentman_flat_plate_coefficients(
        COS_INCIDENCE_ANGLES, HYPERTHERMAL_SPEED_RATIO, reflected
    ).drag_coefficient
    limit = 2 * COS_INCIDENCE_ANGLES + np.sqrt(np.pi) * reflected * COS_INCIDENCE_ANGLES**2
    np.testing.assert_allclose(drag, limit, rtol=1e-6)


@pytest.mark.parametrize("k", BOTH_CONSTANTS)
def test_cooks_reemission_term_differs_from_sentmans_by_a_fixed_factor(k):
    # Sentman re-emits a Maxwellian gas; Cook re-emits every molecule at one speed in a cosine spray.
    # For α < 1 at large s, their re-emission terms differ by 3 sqrt(π k) / 4 (R-04).
    energy_accommodation = 0.9
    sentman = sentman_plate_drag(
        COS_INCIDENCE_ANGLES,
        HYPERTHERMAL_SPEED_RATIO,
        energy_accommodation,
        PLATE_AMBIENT_TEMPERATURE_KELVIN,
        k,
    )
    incident_kinetic_kelvin = (2.0 / 3.0) * HYPERTHERMAL_SPEED_RATIO**2 * PLATE_AMBIENT_TEMPERATURE_KELVIN
    cook = cook_hyperthermal_drag(
        COS_INCIDENCE_ANGLES, energy_accommodation, WALL_TEMPERATURE_KELVIN, incident_kinetic_kelvin
    )
    reemission_ratio = (sentman - 2 * COS_INCIDENCE_ANGLES) / (cook - 2 * COS_INCIDENCE_ANGLES)
    np.testing.assert_allclose(reemission_ratio, 3 * np.sqrt(np.pi * k) / 4, rtol=1e-6)
