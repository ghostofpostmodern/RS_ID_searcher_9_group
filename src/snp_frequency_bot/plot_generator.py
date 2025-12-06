import os
from typing import List

import matplotlib
matplotlib.use("Agg")  # headless backend

import matplotlib.pyplot as plt

from .snp_analyzer import SnpSummary


def generate_plots(summary: SnpSummary, base_dir: str = "/tmp") -> List[str]:
    """Строит базовые графики и возвращает список путей к PNG-файлам."""
    os.makedirs(base_dir, exist_ok=True)
    image_paths: List[str] = []

    if summary.populations:
        studies = [p.study for p in summary.populations]
        ref_freqs = [p.freq_ref for p in summary.populations]
        alt_freqs = [p.freq_alt for p in summary.populations]

        x = range(len(studies))
        plt.figure()
        plt.bar(list(x), ref_freqs)
        plt.bar(list(x), alt_freqs, bottom=ref_freqs)
        plt.xticks(list(x), studies, rotation=45, ha="right")
        plt.ylabel("Allele frequency")
        plt.title(f"Allele frequencies for {summary.rsid}")
        plt.tight_layout()

        path_bar = os.path.join(base_dir, f"{summary.rsid}_alleles.png")
        plt.savefig(path_bar)
        plt.close()
        image_paths.append(path_bar)

    if summary.populations:
        p0 = summary.populations[0]
        geno = p0.genotype_freqs
        labels = ["0/0", "0/1", "1/1"]
        sizes = [geno.hom_ref, geno.het, geno.hom_alt]

        plt.figure()
        plt.pie(sizes, labels=labels, autopct="%1.1f%%")
        plt.title(f"Genotype frequencies ({p0.study}) for {summary.rsid}")
        plt.tight_layout()

        path_pie = os.path.join(base_dir, f"{summary.rsid}_genotypes.png")
        plt.savefig(path_pie)
        plt.close()
        image_paths.append(path_pie)

    return image_paths
