# Stable topology pointers for PartGenome

**Date:** 2026-09-18
**Source of the idea:** `armpro24-blip/cad-cae-copilot`'s `@face:*` pointers
(see [../PRIOR_ART.md](../PRIOR_ART.md)). Reimplemented rather than imported —
that project is v0.1.0-alpha.4 and not a dependency we want between a spec and
a machine that moves metal.
**Implementation:** [`core/topology.py`](../../core/topology.py), 27 tests, no
kernel required.

---

## The failure being prevented

A parametric program says *fillet face 3*. Somebody makes the plate 3 mm
thicker. The kernel re-tessellates and renumbers. Face 3 is now a different
face.

The part still builds. The fillet is on the wrong edge. Nothing reports a
problem, and the first sign of it is a machined part that does not fit.

This is worth stating plainly because index-based selection is the standard way
to do it, and it is silently wrong under **exactly the operation a parametric
model exists to support**. A model you never edit does not need to be
parametric. The one edit it is for is the one that breaks it.

The same failure exists one level up, in the program rather than the kernel:
*the face made by step 3* moves when you insert a step at position 1.

---

## The pointer

    @face:base_pad/top          the face `base_pad` made as its top
    @face:inlet_hole/bore#2     the second bore, where the op makes many
    @edge:base_pad/top_rim      an edge, same grammar

Three parts, and each one is doing work:

| Part | Why |
|---|---|
| `op_id` | a **declared** id, not a position — so inserting a step cannot move it |
| `role` | from a closed vocabulary **we** own, not the kernel's — so renumbering cannot move it |
| `#n` | optional, and required exactly where it is needed |

An op needs an id only if something points at it. You pay for what you name,
and a program with no pointers needs no ids at all.

### The role vocabulary

Kernel-independent names for what each op produces, grown the way `OPS` is
grown in `atlas_cad/part.py` — append, never repurpose, because genomes in the
wild point at these names.

| Op | Faces | Edges |
|---|---|---|
| `pad` | top, bottom, side | top_rim, bottom_rim, side_vertical |
| `pocket` | floor, wall | mouth, floor_rim |
| `hole` | bore, entry, exit, counterbore, countersink | entry_rim, exit_rim |
| `fillet` / `chamfer` | fillet / chamfer | tangent |
| `shell` | inner, outer, opening | opening_rim |
| `rib` | side, top | root |
| `boss` | top, side | top_rim, root |
| `thread` | flank, crest, root | — |
| `sketch` | profile | segment |
| `datum_plane` / `datum_axis` | plane / — | — / axis |

`mirror`, `pattern_linear`, `pattern_circular`, `hole_pattern` and
`pocket_pattern` make no faces of their own. They re-emit the faces of the op
named in `source:`, so the role is checked against *that* op — and because they
always produce more than one instance, **an ordinal is not optional**. "The
bore" of a six-hole pattern is not a thing.

---

## What this buys, in order of value

### 1. The breaking edit stops breaking

Thickening the plate, moving the channel, changing a pattern count — none of
them touch a pointer, because no pointer ever referred to a number the kernel
owns.

### 2. Dangling is loud, and loud at load

Delete the op a pointer names and `check_program` returns a problem naming the
pointer, the step it sits in, and the ids that do exist. This happens next to
the rest of PartGenome's validation, **before any geometry is built** — which
matters because it is the half of the problem that needs no kernel, and
PartGenome's checker is already the strong half.

Also caught at load, all of it kernel-free:

- a role the op does not make (`@face:base_pad/floor` on a pad), with the real
  roles listed
- a face role used as an edge, named as that mistake rather than as "unknown"
- a pointer at a later step, or at its own step
- duplicate op ids
- a pattern that does not declare what it instances

### 3. Ambiguity is an error, not a silent pick

A kernel asked for *the side face* of a four-sided pad hands back the first of
four and carries on. `resolve` raises instead, and names the way out:

    @face:base/side matches 4 faces — say which, e.g. @face:base/side#1

This is the single most important line in the module. Taking the first match is
how the fillet moves.

---

## What it does not buy

An ordinal is only as stable as whatever ordered the instances, and that is the
kernel's business or the pattern's. `Pointer.caveat` says so in the genome's own
voice rather than pretending otherwise:

> `@face:base/side#2` selects by position within a role; it survives a
> dimension change but not a reordering of the instances.

That is the same move `verify_part`'s certificate makes when it names what it
could **not** check. A weaker guarantee stated is worth more than a stronger one
implied.

Two further limits, named rather than buried:

- **The role vocabulary is a promise the compiler has to keep.** A pointer is
  only as good as the kernel adapter that reports "this handle is the top face
  `base_pad` made". `Provenance` is the interface for that; nothing in it is
  implemented yet, because there is no compiler behind `pad` and `pocket` to
  implement it against.
- **This does not solve persistent naming in general.** It sidesteps it. Where
  a face is genuinely the product of several ops interacting — a fillet that
  splits a face in two — the pointer says which op made it and no more.

---

## Where it goes next

`check_program` is written to accept either atlas `FeatureOp` objects or the
plain dicts a YAML load produces, so it drops into `_load_program` in
`atlas_cad/part.py` as one more source of `Finding`s without touching the
loader's shape.

The ordering is deliberate: pointers land **before** the compiler is extended
past its 5 implemented ops, not after. Every op added from here — `hole`,
`fillet`, `chamfer`, `shell`, the patterns — is one that has to report its
provenance, and retrofitting that to a compiler already written is strictly
worse than requiring it of each op as it arrives.
