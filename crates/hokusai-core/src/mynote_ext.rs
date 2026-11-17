//! Thin MyNote integration points; the simulation loop remains in `stroke`.
//!
//! Keep coordinate policy, storage and GPU execution in the consuming host.

use crate::{Brush, BrushState, Dab, TiledSurface};

/// Per-event libmypaint context: positive finite zoom, radians, and turns.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct StrokeInputContext {
    pub view_zoom: f32,
    pub view_rotation: f32,
    pub barrel_rotation: f32,
}

impl Default for StrokeInputContext {
    fn default() -> Self {
        Self {
            view_zoom: 1.0,
            view_rotation: 0.0,
            barrel_rotation: 0.0,
        }
    }
}

/// Additional per-stroke context, isolated from upstream's state fields.
#[derive(Debug, Clone, Default)]
pub struct StrokeContextState {
    pub barrel_rotation: f32,
    pub last_input_context: StrokeInputContext,
    pub last_xtilt: f32,
    pub last_ytilt: f32,
}

impl Brush {
    /// Original upstream entry point; context comes from the host Surface.
    /// No borrowed Surface or callback survives this synchronous call.
    #[allow(clippy::too_many_arguments)]
    pub fn stroke_to<S: TiledSurface>(
        &self,
        state: &mut BrushState,
        surface: &mut S,
        x: f32,
        y: f32,
        pressure: f32,
        xtilt: f32,
        ytilt: f32,
        dtime: f64,
    ) -> bool {
        let context = surface.stroke_input_context();
        self.stroke_to_with_context(state, surface, x, y, pressure, xtilt, ytilt, dtime, context)
    }
}

/// Complete version-1 GPU Dab transport. Exhaustive destructuring makes new
/// upstream fields a compilation failure, never an unnoticed dropped feature.
/// Pixel execution and interpretation of this wire layout stay in the host.
pub fn packed_dab(dab: &Dab) -> [f32; 20] {
    let Dab {
        x,
        y,
        radius,
        color,
        opaque,
        hardness,
        alpha_eraser,
        aspect_ratio,
        angle,
        lock_alpha,
        colorize,
        posterize,
        posterize_num,
        paint,
        anti_aliasing,
    } = *dab;
    [
        x,
        y,
        radius,
        hardness,
        color.r,
        color.g,
        color.b,
        color.a,
        opaque,
        aspect_ratio,
        angle,
        anti_aliasing,
        alpha_eraser,
        lock_alpha,
        colorize,
        posterize,
        posterize_num,
        paint,
        0.0,
        0.0,
    ]
}

pub(crate) static TRACE_INPUTS: std::sync::LazyLock<bool> =
    std::sync::LazyLock::new(|| std::env::var("HOKUSAI_TRACE_INPUTS").is_ok());

/// mypaint-brush.c:1303-1322: clamp each axis, not the combined magnitude.
/// C uses 90 for both no-tilt axis targets and double atan2/hypot otherwise.
pub(crate) fn tilt_inputs(xtilt: f32, ytilt: f32) -> (f32, f32, f32, f32, f32) {
    if xtilt == 0.0 && ytilt == 0.0 {
        (0.0, 90.0, 0.0, 90.0, 90.0)
    } else {
        let xtilt = xtilt.clamp(-1.0, 1.0);
        let ytilt = ytilt.clamp(-1.0, 1.0);
        let magnitude = (xtilt as f64).hypot(ytilt as f64) as f32;
        let ascension =
            ((-(xtilt as f64)).atan2(ytilt as f64) / (2.0 * std::f64::consts::PI) * 360.0) as f32;
        (
            magnitude,
            90.0 - magnitude * 60.0,
            ascension,
            xtilt * 60.0,
            ytilt * 60.0,
        )
    }
}

/// C `DEGREES(x)` — evaluated in double; callers narrow at assignment.
#[inline]
pub(crate) fn degrees_c(x: f32) -> f64 {
    x as f64 / (2.0 * std::f64::consts::PI) * 360.0
}

/// C `RADIANS(x)` — evaluated in double, narrowed to f32.
#[inline]
pub(crate) fn radians_c(x: f32) -> f32 {
    (x as f64 * std::f64::consts::PI / 180.0) as f32
}

/// C mod_arith: f32 division, double floor/multiply/subtract, then narrowing.
#[inline]
pub(crate) fn mod_arith_c(a: f32, n: f32) -> f32 {
    (a as f64 - n as f64 * (a / n).floor() as f64) as f32
}

/// Query mapping requirements once when compiling an immutable host brush.
/// No mutable cache is added to the upstream Brush type.
pub fn required_grid_axes(brush: &Brush) -> u8 {
    let mut axes = 0;
    for mapping in brush.settings().iter().flat_map(|setting| &setting.inputs) {
        axes |= match mapping.input {
            crate::BrushInput::GridmapX => 1,
            crate::BrushInput::GridmapY => 2,
            _ => 0,
        };
        if axes == 3 {
            break;
        }
    }
    axes
}
