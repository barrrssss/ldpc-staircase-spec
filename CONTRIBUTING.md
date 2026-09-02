# Contributing

This repository holds the normative specification and the conformance vectors for
ldpc-staircase. It is the contract the independent implementations are measured against, so
changes here are heavier than changes to a library.

## What a change to this repository means

- **A change to `SPEC.md` or to a committed vector is a specification change.** It
  obliges every implementation to follow, and it advances the specification version.
- **Vectors are generated, never hand-edited.** They come from a single authorized
  generator. A hand-written or hand-corrected vector destroys the only property that
  makes two independent implementations comparable: that neither of them produced the
  oracle.
- **Additive is the goal.** A change leaving every previously committed vector
  byte-identical lets existing implementations pass unchanged. A change that alters an
  existing vector is a compatibility break, and needs a far stronger justification than
  a better idea.

The most valuable contributions here are usually not new features. They are:

- an ambiguity in `SPEC.md` that two careful readers could implement differently;
- a case the committed vectors do not actually exercise, with the reasoning for why it
  matters;
- an independent implementation, written from the specification text alone, that
  disagrees with the vectors. That is a finding, and a welcome one.

## Reporting an ambiguity

Open an issue quoting the section and stating the two readings you think the text
permits. A specification defect report does not need a patch attached; identifying the
fork precisely is the hard part.

For a suspected security issue, follow [`SECURITY.md`](SECURITY.md) instead of opening
a public issue.

## License

Contributions are accepted under the [Apache License 2.0](LICENSE), the license this
project is released under. The specification is deliberately on the same terms as the
implementations, because independent implementations work from this document.
