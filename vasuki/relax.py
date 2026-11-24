
"""Restrained energy minimisation of MODELLER models (OpenMM).

MODELLER optimises its own restraint-based objective function, not stereochemical
quality as judged by MolProbity, so raw models usually carry steric clashes and
strained side chains. This step adds hydrogens, then minimises the structure in the
AMBER force field (implicit solvent) while holding the heavy atoms close to their
starting positions: strongly on the backbone, weakly on the side chains. The fold is
kept; clashes and local geometry are relaxed.

Requires:  pip install openmm pdbfixer
"""
import os

KCAL_PER_A2_TO_KJ_PER_NM2 = 4.184 * 100.0   # 1 kcal/mol/A^2 = 418.4 kJ/mol/nm^2
BACKBONE = {"N", "CA", "C", "O"}


def relax_pdb(in_pdb, out_pdb, backbone_k=10.0, sidechain_k=1.0,
              max_iterations=1000, keep_hydrogens=False, log=print):
    """Minimise `in_pdb` and write the result to `out_pdb`.

    backbone_k / sidechain_k: restraint force constants in kcal/mol/A^2.
    keep_hydrogens: write hydrogens to the output (default: heavy atoms only,
                    so MolProbity/Reduce adds its own hydrogens).
    Returns a dict with energies (kJ/mol) and RMSDs (A) to the input structure.
    """
    try:
        import numpy as np
        from openmm import (CustomExternalForce, LangevinMiddleIntegrator, unit)
        from openmm import app
        from pdbfixer import PDBFixer
    except ImportError as e:
        raise ImportError(
            "Relaxation needs OpenMM and PDBFixer: pip install openmm pdbfixer "
            f"({e})")

    # --- 1. complete the structure (missing atoms, terminal OXT, hydrogens)
    fixer = PDBFixer(filename=in_pdb)
    fixer.missingResidues = {}                    # never invent whole residues
    fixer.findNonstandardResidues()
    fixer.replaceNonstandardResidues()
    fixer.findMissingAtoms()
    fixer.addMissingAtoms()
    fixer.addMissingHydrogens(7.0)

    topology, positions = fixer.topology, fixer.positions

    # --- 2. force field: AMBER14 + implicit solvent (GBn2)
    ff = app.ForceField("amber14-all.xml", "implicit/gbn2.xml")
    system = ff.createSystem(topology,
                             nonbondedMethod=app.CutoffNonPeriodic,
                             nonbondedCutoff=1.2 * unit.nanometer,
                             constraints=None)

    # --- 3. position restraints on heavy atoms (backbone stiff, side chains soft)
    restraint = CustomExternalForce(
        "0.5*k*((x-x0)^2+(y-y0)^2+(z-z0)^2)")
    restraint.addPerParticleParameter("k")
    restraint.addPerParticleParameter("x0")
    restraint.addPerParticleParameter("y0")
    restraint.addPerParticleParameter("z0")
    pos_nm = positions.value_in_unit(unit.nanometer)
    heavy_idx = []
    for atom in topology.atoms():
        if atom.element is None or atom.element.symbol == "H":
            continue
        k = backbone_k if atom.name in BACKBONE else sidechain_k
        x, y, z = pos_nm[atom.index]
        restraint.addParticle(atom.index,
                              [k * KCAL_PER_A2_TO_KJ_PER_NM2, x, y, z])
        heavy_idx.append(atom.index)
    system.addForce(restraint)

    # --- 4. minimise
    integrator = LangevinMiddleIntegrator(300 * unit.kelvin,
                                          1.0 / unit.picosecond,
                                          0.002 * unit.picoseconds)
    sim = app.Simulation(topology, system, integrator)
    sim.context.setPositions(positions)
    e0 = sim.context.getState(getEnergy=True).getPotentialEnergy()
    log(f"  relax: {len(heavy_idx)} heavy atoms, start energy "
        f"{e0.value_in_unit(unit.kilojoule_per_mole):.0f} kJ/mol")
    sim.minimizeEnergy(
        tolerance=10 * unit.kilojoule_per_mole / unit.nanometer,
        maxIterations=max_iterations)
    state = sim.context.getState(getEnergy=True, getPositions=True)
    e1 = state.getPotentialEnergy()
    new_pos = state.getPositions()

    # --- 5. report movement (heavy atoms and CA)
    a = np.array([pos_nm[i] for i in heavy_idx]) * 10.0
    b = np.array([new_pos.value_in_unit(unit.nanometer)[i] for i in heavy_idx]) * 10.0
    rmsd_heavy = float(np.sqrt(((a - b) ** 2).sum(axis=1).mean()))
    ca = [at.index for at in topology.atoms() if at.name == "CA"]
    npn = new_pos.value_in_unit(unit.nanometer)
    rmsd_ca = float(np.sqrt(np.mean([
        sum((10.0 * (pos_nm[i][d] - npn[i][d])) ** 2 for d in range(3))
        for i in ca]))) if ca else 0.0

    # --- 6. write result
    out_top, out_pos = topology, new_pos
    if not keep_hydrogens:
        modeller = app.Modeller(topology, new_pos)
        modeller.delete([at for at in topology.atoms()
                         if at.element is not None and at.element.symbol == "H"])
        out_top, out_pos = modeller.topology, modeller.positions
    os.makedirs(os.path.dirname(os.path.abspath(out_pdb)), exist_ok=True)
    with open(out_pdb, "w") as fh:
        app.PDBFile.writeFile(out_top, out_pos, fh, keepIds=True)

    info = {
        "energy_before": e0.value_in_unit(unit.kilojoule_per_mole),
        "energy_after": e1.value_in_unit(unit.kilojoule_per_mole),
        "rmsd_heavy": rmsd_heavy,
        "rmsd_ca": rmsd_ca,
    }
    log(f"  relax: energy {info['energy_before']:.0f} -> {info['energy_after']:.0f} kJ/mol, "
        f"heavy-atom RMSD {rmsd_heavy:.2f} A, CA RMSD {rmsd_ca:.2f} A")
    return info


def _main(argv=None):
    """Command line entry point; VASUKI runs this in a separate process:
        python relax.py model.pdb model_relaxed.pdb [--iterations 500]"""
    import argparse
    ap = argparse.ArgumentParser(description="Restrained minimisation of a model (OpenMM).")
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--iterations", type=int, default=500)
    ap.add_argument("--backbone-k", type=float, default=10.0)
    ap.add_argument("--sidechain-k", type=float, default=1.0)
    ap.add_argument("--keep-h", action="store_true")
    a = ap.parse_args(argv)
    relax_pdb(a.input, a.output, backbone_k=a.backbone_k, sidechain_k=a.sidechain_k,
              max_iterations=a.iterations, keep_hydrogens=a.keep_h,
              log=lambda s: print(s, flush=True))


if __name__ == "__main__":
    _main()