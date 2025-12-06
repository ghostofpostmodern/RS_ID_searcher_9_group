from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class GenotypeFrequencies:
    hom_ref: float
    het: float
    hom_alt: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PopulationSummary:
    study: str
    ref_allele: str
    alt_allele: str
    freq_ref: float
    freq_alt: float
    genotype_freqs: GenotypeFrequencies
    total_alleles: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["genotype_freqs"] = self.genotype_freqs.to_dict()
        return d


@dataclass
class SnpSummary:
    rsid: str
    populations: List[PopulationSummary]


def _compute_hardy_weinberg(p: float, q: float) -> GenotypeFrequencies:
    return GenotypeFrequencies(
        hom_ref=p * p,
        het=2 * p * q,
        hom_alt=q * q,
    )


def summarize_snp(rsid: str, raw: Dict[str, Any]) -> SnpSummary:
    """Упрощённый парсер структуры ответа NCBI dbSNP.

    Структура API может меняться, поэтому здесь используются защитные .get()
    и фильтрация по наличию частот. При необходимости логику парсинга
    нужно уточнить под реальный формат JSON.
    """
    primary = raw.get("primary_snapshot_data", {})
    allele_annotations = primary.get("allele_annotations", [])

    populations: List[PopulationSummary] = []

    for ann in allele_annotations:
        freqs = ann.get("frequency", [])
        for freq in freqs:
            study = freq.get("study_name") or "unknown"
            allele = freq.get("allele")
            if allele is None:
                continue
            try:
                alt_freq = float(freq.get("frequency"))
                ref_freq = 1.0 - alt_freq
            except (TypeError, ValueError):
                continue

            allele_number = freq.get("allele_number") or 0

            geno = _compute_hardy_weinberg(ref_freq, alt_freq)

            populations.append(
                PopulationSummary(
                    study=study,
                    ref_allele="REF",
                    alt_allele=str(allele),
                    freq_ref=ref_freq,
                    freq_alt=alt_freq,
                    genotype_freqs=geno,
                    total_alleles=int(allele_number),
                )
            )

    return SnpSummary(rsid=rsid, populations=populations)
