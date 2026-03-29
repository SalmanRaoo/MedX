import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import DoctorWorkspaceLayout from "../../components/dashboards/DoctorWorkspaceLayout";
import { aiApi } from "../../lib/api";

const SYMPTOMS = [
  "fever",
  "cough",
  "fatigue",
  "body_pain",
  "runny_nose",
  "chills",
  "headache",
  "weight_loss",
  "high_fever",
  "sweating",
  "nausea",
  "joint_pain",
  "vomiting",
  "rash",
  "abdominal_pain",
  "diarrhea",
  "yellowish_skin",
  "chest_pain",
  "breathlessness",
  "itching",
  "skin_rash",
  "bumps",
  "acidity",
  "indigestion",
  "burning_chest",
  "swelling",
];

function normalizeKey(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/_+/g, "_");
}

function prettyLabel(value) {
  return value.replaceAll("_", " ");
}

export default function DoctorSymptomsPage() {
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  const symptomOptions = useMemo(() => {
    const unique = Array.from(new Set(SYMPTOMS.map((s) => normalizeKey(s)).filter(Boolean)));
    unique.sort((a, b) => a.localeCompare(b));
    return unique;
  }, []);

  const filtered = useMemo(() => {
    if (!query.trim()) return symptomOptions;
    const q = normalizeKey(query);
    return symptomOptions.filter((s) => s.includes(q));
  }, [query, symptomOptions]);

  const selectedSet = useMemo(() => new Set(selected), [selected]);

  const toggleSymptom = (symptom) => {
    setSelected((prev) => (prev.includes(symptom) ? prev.filter((s) => s !== symptom) : [...prev, symptom]));
  };

  const clearAll = () => {
    setSelected([]);
    setResult(null);
    setError("");
  };

  const submitPrediction = async () => {
    if (!selected.length) {
      setError("Select at least one symptom.");
      return;
    }

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const res = await aiApi.post("/predict/disease", { symptoms: selected });
      setResult(res.data || null);
    } catch (err) {
      setError(err?.response?.data?.detail || "Unable to connect to AI service.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <DoctorWorkspaceLayout
      title="Symptoms Diagnosis"
      subtitle="Search symptoms, select quickly, and send to disease predictor model."
    >
      <div className="grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="relative block">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symptoms"
              className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-sm outline-none focus:border-cyan-500"
            />
          </label>

          <div className="mt-4 h-[26rem] overflow-auto rounded-xl border border-slate-200 p-2">
            <div className="grid gap-2 sm:grid-cols-2">
              {filtered.map((symptom) => (
                <label key={symptom} className="flex items-start gap-2 rounded-lg border border-slate-200 p-2 text-sm">
                  <input
                    type="checkbox"
                    checked={selectedSet.has(symptom)}
                    onChange={() => toggleSymptom(symptom)}
                    className="mt-1"
                  />
                  <span>{prettyLabel(symptom)}</span>
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-slate-500">Selected Symptoms</h3>
              <button type="button" onClick={clearAll} className="text-xs font-semibold text-rose-600 hover:text-rose-700">Clear</button>
            </div>
            {selected.length ? (
              <div className="flex max-h-48 flex-wrap gap-2 overflow-auto">
                {selected.map((symptom) => (
                  <button
                    key={symptom}
                    type="button"
                    onClick={() => toggleSymptom(symptom)}
                    className="inline-flex items-center gap-1 rounded-full border border-cyan-300 bg-cyan-50 px-3 py-1 text-xs font-semibold text-cyan-700"
                  >
                    {prettyLabel(symptom)} <X className="h-3 w-3" />
                  </button>
                ))}
              </div>
            ) : (
              <p className="text-sm text-slate-500">No symptoms selected yet.</p>
            )}

            <button
              type="button"
              onClick={submitPrediction}
              disabled={loading || selected.length === 0}
              className="mt-4 w-full rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white hover:bg-cyan-700 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {loading ? "Predicting..." : "Predict Disease"}
            </button>

            {error ? <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
          </div>

          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <h3 className="text-sm font-bold uppercase tracking-[0.12em] text-slate-500">Model Result</h3>
            {result ? (
              <div className="mt-3 space-y-2 text-sm">
                <p><span className="font-semibold">Prediction:</span> {result.prediction || "N/A"}</p>
                <p><span className="font-semibold">Confidence:</span> {result.confidence || "N/A"}</p>
                <p><span className="font-semibold">Matched Features:</span> {result.matched_count ?? 0}</p>
                {Array.isArray(result.unknown_symptoms) && result.unknown_symptoms.length ? (
                  <p className="text-amber-700"><span className="font-semibold">Ignored:</span> {result.unknown_symptoms.join(", ")}</p>
                ) : null}
              </div>
            ) : (
              <p className="mt-2 text-sm text-slate-500">Run a prediction to see output here.</p>
            )}
          </div>
        </div>
      </div>
    </DoctorWorkspaceLayout>
  );
}

