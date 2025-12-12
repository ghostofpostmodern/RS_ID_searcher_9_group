import os
from typing import List
from .snp_analyzer import SnpSummary

import matplotlib
matplotlib.use("Agg")  # headless backend

import matplotlib.pyplot as plt

PLOTS_DIR = "plots"

def generate_plots(summary: SnpSummary) -> List[str]:
    os.makedirs(PLOTS_DIR, exist_ok=True)

    paths: List[str] = []

    studies = [p.study for p in summary.populations]
    ref_freqs = [p.freq_ref for p in summary.populations]
    alt_freqs = [p.freq_alt for p in summary.populations]

    # ============================================================
    # 1) Барчарт аллельных частот (stacked bar)
    # ============================================================
    if studies:
        fig, ax = plt.subplots(figsize=(14, 9), dpi=150)

        x = range(len(studies))
        ax.bar(x, ref_freqs, label="Ref allele", width=0.8)
        ax.bar(x, alt_freqs, bottom=ref_freqs, label="Alt allele", width=0.8)

        ax.set_title(f"Allele frequencies for {summary.rsid}")
        ax.set_ylabel("Allele frequency")
        ax.set_xticks(list(x))
        ax.set_xticklabels(studies, rotation=70, ha="right", fontsize=8)

        ax.legend()
        plt.tight_layout()

        bar_path = os.path.join(PLOTS_DIR, f"{summary.rsid}_alleles.png")
        fig.savefig(bar_path)
        plt.close(fig)
        paths.append(bar_path)

    # ============================================================
    # 2) MAF по популяциям
    # ============================================================
    if studies:
        maf_vals = [min(r, a) for r, a in zip(ref_freqs, alt_freqs)]

        fig_maf, ax_maf = plt.subplots(figsize=(14, 9), dpi=150)

        x = range(len(studies))
        ax_maf.bar(x, maf_vals, width=0.7)

        ax_maf.set_title(f"Minor Allele Frequency (MAF) for {summary.rsid}")
        ax_maf.set_ylabel("MAF")
        ax_maf.set_xticks(list(x))
        ax_maf.set_xticklabels(studies, rotation=70, ha="right", fontsize=8)

        plt.tight_layout()

        maf_path = os.path.join(PLOTS_DIR, f"{summary.rsid}_maf.png")
        fig_maf.savefig(maf_path)
        plt.close(fig_maf)
        paths.append(maf_path)

    # ============================================================
    # 3) Pie chart генотипных частот по первой популяции (если есть)
    # ============================================================
    if summary.populations:
        p0 = summary.populations[0]
        gf = p0.genotype_freqs

        if gf:
            fig2, ax2 = plt.subplots(figsize=(10, 10), dpi=150)

            labels = ["0/0", "0/1", "1/1"]
            sizes = [gf.hom_ref, gf.het, gf.hom_alt]

            ax2.pie(
                sizes,
                labels=[f"{l}\n{v*100:.1f}%" for l, v in zip(labels, sizes)],
                autopct=None,
            )
            ax2.set_title(f"Genotype frequencies ({p0.study}) for {summary.rsid}")

            plt.tight_layout()

            pie_path = os.path.join(PLOTS_DIR, f"{summary.rsid}_genotypes.png")
            fig2.savefig(pie_path)
            plt.close(fig2)
            paths.append(pie_path)

    return paths
