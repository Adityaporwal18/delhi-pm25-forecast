import { z } from "zod";

/** The FastAPI backend's responses, checked when they arrive (src/delhi_pm25/api.py). */
const value = z.number().nullable();
const stationSchema = z.object({ slug: z.string(), name: z.string(), latitude: z.number(), longitude: z.number() });
const categorySchema = z.object({ label: z.string(), upper_ug_m3: z.number().nullable(), colour: z.string() });

const metaSchema = z.object({
  issue_times_utc: z.array(z.string()),
  horizons_h: z.array(z.number().int()),
  stations: z.array(stationSchema),
  categories: z.array(categorySchema),
  credits: z.string(),
  note: z.string(),
});
const mapPointSchema = z.object({
  slug: z.string(),
  p10: value,
  p50: value,
  p90: value,
  measured: value,
  category: z.string().nullable(),
  colour: z.string().nullable(),
});
const forecastPointSchema = z.object({
  horizon_h: z.number().int(),
  valid_utc: z.string(),
  p10: value,
  p50: value,
  p90: value,
  measured: value,
});

export type Meta = z.infer<typeof metaSchema>;
export type Station = z.infer<typeof stationSchema>;
export type Category = z.infer<typeof categorySchema>;
export type MapPoint = z.infer<typeof mapPointSchema>;
export type ForecastPoint = z.infer<typeof forecastPointSchema>;

export class ApiError extends Error {
  override name = "ApiError";
}

async function getJson<T>(url: string, schema: z.ZodType<T>, signal: AbortSignal): Promise<T> {
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new ApiError(`The server answered ${response.status} for ${url}`);
  }
  return schema.parse(await response.json());
}

export function fetchMeta(signal: AbortSignal): Promise<Meta> {
  return getJson("/api/meta", metaSchema, signal);
}

export function fetchMap(issued: string, horizon: number, signal: AbortSignal): Promise<MapPoint[]> {
  const query = new URLSearchParams({ issued, horizon: String(horizon) });
  return getJson(`/api/map?${query.toString()}`, z.array(mapPointSchema), signal);
}

export function fetchForecast(slug: string, issued: string, signal: AbortSignal): Promise<ForecastPoint[]> {
  const query = new URLSearchParams({ issued });
  return getJson(`/api/stations/${encodeURIComponent(slug)}/forecast?${query.toString()}`, z.array(forecastPointSchema), signal);
}

const livePointSchema = forecastPointSchema.extend({
  slug: z.string(),
  category: z.string().nullable(),
  colour: z.string().nullable(),
});
const liveSchema = z.object({
  generated_at_utc: z.string(),
  issued_utc: z.string(),
  stations_reporting: z.number().int(),
  stations: z.number().int(),
  training_window: z.object({ first_target_utc: z.string(), last_target_utc: z.string() }),
  rows: z.array(livePointSchema),
  city_median_now: z.number().nullable(),
  heavy_smog_now: z.boolean(),
  station_status: z.array(
    z.object({
      slug: z.string(),
      status: z.enum(["reporting", "set_aside", "analyser_dark", "delayed", "silent"]),
      last_value: z.number().nullable(),
      last_value_utc: z.string().nullable(),
      last_reading_utc: z.string().nullable(),
    }),
  ),
});
const accuracySchema = z.object({
  source: z.string(),
  horizons: z.array(
    z.object({
      horizon_h: z.number().int(),
      model_mae: z.number(),
      persistence_mae: z.number(),
      climatology_mae: z.number(),
      inside_band_pct: z.number(),
      inside_band_smoggiest_10pct: z.number(),
    }),
  ),
  smoggiest_10pct_48h: z.object({
    model_mae: z.number(),
    climatology_mae: z.number(),
    persistence_mae: z.number(),
    model_bias: z.number(),
  }),
});

export type LivePoint = z.infer<typeof livePointSchema>;
export type Live = z.infer<typeof liveSchema>;
export type Accuracy = z.infer<typeof accuracySchema>;

/** The latest live forecast (503 while none has been published). */
export function fetchLive(signal: AbortSignal): Promise<Live> {
  return getJson("/api/live", liveSchema, signal);
}

/** The evaluation model's held-out 2025 accuracy: the only accuracy numbers the site shows. */
export function fetchAccuracy(signal: AbortSignal): Promise<Accuracy> {
  return getJson("/api/accuracy", accuracySchema, signal);
}
