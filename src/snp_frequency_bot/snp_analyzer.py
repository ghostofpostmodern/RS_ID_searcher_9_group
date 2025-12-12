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
    """
    Разбор ответа NCBI dbSNP.

    Берём частоты из:
      primary_snapshot_data.allele_annotations[*].frequency[*]

    Используем схему:
      MAF = allele_count / total_count
      ref_allele = observation.deleted_sequence
      alt_allele = observation.inserted_sequence
    """
    primary = raw.get("primary_snapshot_data", {})
    allele_annotations = primary.get("allele_annotations", [])

    populations: List[PopulationSummary] = []

    for ann in allele_annotations:
        freqs = ann.get("frequency") or []
        for freq in freqs:
            obs = freq.get("observation") or {}
            study = freq.get("study_name") or "unknown"

            ref_seq = obs.get("deleted_sequence")
            alt_seq = obs.get("inserted_sequence")

            allele_count = freq.get("allele_count")
            total_count = freq.get("total_count")

            # базовая защита от мусора
            if (
                allele_count is None
                or total_count in (None, 0)
            ):
                continue

            try:
                allele_count = float(allele_count)
                total_count = float(total_count)
                maf = allele_count / total_count
            except (TypeError, ValueError, ZeroDivisionError):
                continue

            # если каких-то последовательностей нет — всё равно берём, как есть
            ref_allele = ref_seq or "-"
            alt_allele = alt_seq or "-"

            alt_freq = float(maf)
            ref_freq = max(0.0, 1.0 - alt_freq)

            geno = _compute_hardy_weinberg(ref_freq, alt_freq)

            populations.append(
                PopulationSummary(
                    study=study,
                    ref_allele=ref_allele,
                    alt_allele=alt_allele,
                    freq_ref=ref_freq,
                    freq_alt=alt_freq,
                    genotype_freqs=geno,
                    total_alleles=int(total_count),
                )
            )

    return SnpSummary(rsid=rsid, populations=populations)
