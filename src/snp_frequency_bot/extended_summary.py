from typing import Any, Dict, List

from .snp_analyzer import SnpSummary


def _extract_basic_info(rsid: str, raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Пытаемся аккуратно вытащить базовую информацию:
    - variant_type
    - chromosome
    - position (GRCh38, если есть)
    - genes
    - HGVS c. / p.
    - region (exon/intron/UTR/near-splice/other)
    Всё делаем максимально безопасно: если чего-то нет, подставляем '-'.
    """
    primary = raw.get("primary_snapshot_data", {}) or {}

    # 1) Variant type (если есть)
    variant_type = raw.get("variant_type") or primary.get("variant_type") or "-"

    # 2) Chromosome & position (берём первую подходящую placement, лучше GRCh38)
    chrom = "-"
    pos38 = "-"
    placements = primary.get("placements_with_allele", []) or []
    # эвристика: ищем human, GRCh38, is_ptlp == True
    for pl in placements:
        try:
            asm = pl.get("placement_annot", {}).get("assembly_name", "")
            is_grch38 = "GRCh38" in asm
            is_ptlp = pl.get("is_ptlp", False)
            locs = pl.get("alleles", [])[0].get("allele", {}).get("spdi", {})
            # spdi: "seq_id", "position", "deleted_sequence", "inserted_sequence"
            seq_id = locs.get("seq_id")
            pos = locs.get("position")
            if is_grch38 and is_ptlp and seq_id is not None and pos is not None:
                chrom = str(seq_id)
                pos38 = str(pos)
                break
        except Exception:
            continue

    # 3) Genes: собираем все уникальные символы генов, если есть
    genes: List[str] = []
    allele_annotations = primary.get("allele_annotations", []) or []
    for ann in allele_annotations:
        gene_info = ann.get("gene") or ann.get("genes")
        if isinstance(gene_info, dict):
            symbol = gene_info.get("symbol")
            if symbol and symbol not in genes:
                genes.append(symbol)
        elif isinstance(gene_info, list):
            for g in gene_info:
                symbol = g.get("symbol")
                if symbol and symbol not in genes:
                    genes.append(symbol)

    if not genes:
        genes = ["-"]

    # 4) HGVS: ищем coding (c.) и protein (p.) среди референсов
    hgvs_c = "-"
    hgvs_p = "-"
    hgvs_list = raw.get("hgvs", []) or []
    # Вариант 1: если NCBI отдаёт список hgvs
    for h in hgvs_list:
        s: str = str(h)
        if ":c." in s and hgvs_c == "-":
            hgvs_c = s
        if ":p." in s and hgvs_p == "-":
            hgvs_p = s
    # Вариант 2: через клинические / реф-аннотации — на всякий случай можно добавить позже

    # 5) Region — пока ставим грубо '-', здесь можно позже доразобрать locations
    # (exon/intron/UTR/near-splice...)
    region = "-"

    return {
        "rsid": rsid,
        "variant_type": variant_type,
        "chrom": chrom,
        "pos38": pos38,
        "genes": genes,
        "hgvs_c": hgvs_c,
        "hgvs_p": hgvs_p,
        "region": region,
    }


def _categorize_maf(maf: float) -> str:
    """
    Простая категоризация MAF:
    <0.001 ultra-rare
    <0.01  rare
    <0.05  low-frequency
    >=0.05 common
    """
    if maf < 0.001:
        return "ultra-rare"
    if maf < 0.01:
        return "rare"
    if maf < 0.05:
        return "low-frequency"
    return "common"


def _build_population_blocks(summary: SnpSummary) -> List[Dict[str, Any]]:
    """
    Обогащаем популяции:
    - p, q
    - maf
    - sample_n (по allele_number ~ total_alleles/2)
    - category по maf
    - source(=study) и name(=study)
    """
    populations: List[Dict[str, Any]] = []
    for p in summary.populations:
        p_freq = float(p.freq_ref)
        q_freq = float(p.freq_alt)
        maf = float(min(p_freq, q_freq))
        # total_alleles ~ 2 * sample_n при диплоидном геноме
        sample_n = p.total_alleles // 2 if p.total_alleles else 0
        category = _categorize_maf(maf)

        populations.append(
            {
                "name": p.study,
                "source": p.study,
                "ref_allele": p.ref_allele,
                "alt_allele": p.alt_allele,
                "p": p_freq,
                "q": q_freq,
                "maf": maf,
                "sample_n": sample_n,
                "category": category,
            }
        )

    return populations


def build_extended_summary(
    rsid: str,
    raw: Dict[str, Any],
    summary: SnpSummary,
) -> Dict[str, Any]:
    """
    Собираем расширенную сводку по варианту:
    - basic_info: gene, HGVS, chrom/pos, type, region
    - populations: p, q, maf, sample_n, category, source
    - warnings: список текстовых предупреждений
    """
    basic_info = _extract_basic_info(rsid, raw)
    populations = _build_population_blocks(summary)

    warnings: List[str] = []

    # Проверка: меняется ли минорный аллель между популяциями?
    minor_alleles = set()
    for pop in populations:
        p_freq = pop["p"]
        q_freq = pop["q"]
        if p_freq <= q_freq:
            minor_alleles.add(pop["ref_allele"])
        else:
            minor_alleles.add(pop["alt_allele"])

    if len(minor_alleles) > 1:
        warnings.append(
            "Minor allele differs between populations (possible allele flip between cohorts)."
        )

    return {
        "basic_info": basic_info,
        "populations": populations,
        "warnings": warnings,
    }
