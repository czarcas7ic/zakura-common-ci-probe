# Aeneas proofs of Common's Udon arithmetic

This package ports the Udon arithmetic proofs to Common's production source
at revision `30eeb939123414887642f1cdb60ea59ab13bdf7c`. It extracts the actual
Rust module with Charon and Aeneas and checks the proof terms with Lean.
Production arithmetic is unchanged by this package.

The first layer proves these routines for every valid input:

| Routine | Proven result, with `B = 2^64` |
| --- | --- |
| `adc` | Low remainder and high quotient of `lhs + rhs + carry` |
| `mac` | Low remainder and high quotient of `lhs * rhs + accumulator + carry` |
| `sbb` | Borrow at most one and `low + rhs + borrow = lhs + B * outgoing_borrow`, assuming incoming borrow at most one |
| `carry_add` | `low + B * outgoing_carry = lhs + rhs + incoming_carry` |
| `wide_mul` | Low remainder and high quotient of `lhs * rhs` |

These contracts include successful execution with overflow checks and debug
assertions enabled. The word-layer census checks 13 declarations, including
the supporting arithmetic identities and flag-disjointness proofs.

The second layer proves every shared multi-limb routine for arbitrary limb
values, including both of Common's new flag-carried chains. Write `val4` and
`val8` for the natural numbers represented by four and eight little-endian
limbs, and `R = B^4`:

| Routine | Proven result |
| --- | --- |
| `compare_limbs` | Returned ordering agrees with `val4` |
| `add_limbs` | `val4(out) + R * carry = val4(lhs) + val4(rhs)`, carry at most one |
| `subtract_limbs` | `val4(out) + val4(rhs) = val4(lhs) + R * borrow`, borrow at most one |
| `carry_add_limbs` | Exact addition identity with a Boolean carry |
| `borrow_sub_limbs` | Exact subtraction identity with a Boolean borrow |
| `multiply_wide` | `val8(out) = val4(lhs) * val4(rhs)` |
| `square_wide` | `val8(out) = val4(value)^2` |

The complete two-layer census checks 40 declarations, including the loop
unfoldings and integer bounds. These proofs use the actual production module
directly, with its debug assertions enabled.
The third layer proves every portable Montgomery kernel, including Common's
new split-product multiplier and flag-carried modular addition and subtraction.
Write `p` for the selected modulus:

| Routine | Input bound and proven result |
| --- | --- |
| `reduce_once` | Below `2p`; result is `input mod p`, below `p` |
| `reduce_twice_modulus` | Five-word input below `4p`; result is `input mod 2p`, below `2p` |
| `add_twice_modulus`, `_rust` | Both inputs below `2p`; their sum modulo `2p`, below `2p` |
| `sub_twice_modulus`, `_rust` | Both inputs below `2p`; result plus `rhs` agrees with `lhs` modulo `2p`, below `2p` |
| `montgomery_reduce_unreduced` | `T < pR + p²`; result below `3p`, with `R·out = T + m·p` and `m < R` |
| `montgomery_reduce` | `T < pR`; canonical Montgomery result below `p` |
| `montgomery_multiply` | Both operands below `2p`, or product below `pR`; result below `2p`, with `R·out = lhs·rhs + m·p` and `m < R` |
| `montgomery_multiply_loose`, `_rust` | Both operands below `2p`; the same exact Montgomery equation and result bound |
| `montgomery_square` | Input below `2p`; the Montgomery square equation and result below `2p` |
| `square_run` | Every `usize` count and either final-factor branch; loose bounds and the weighted power congruence |

The fast multiplier's proof checks every wide product and split carry chain,
the omitted cancelled low product, all three zero-carry assertions per round,
both public input-bound assertions and the four-round composition. The existing
Pasta closure theorem gives the sharper result bound below `2p`.
Repeated squaring proves `R^(2^n-1)·out ≡ value^(2^n) mod p` without a factor,
and `R^(2^n)·out ≡ value^(2^n)·factor mod p` with a factor.

The harness imports production `word.rs` and `montgomery.rs` and derives its
concrete prime dictionaries from the pinned `parameters.rs`. Lean checks their
modulus shape, inverse, doubled modulus and closure inequalities.
[KernelBridge.lean](proofs/KernelBridge.lean) proves the definitional agreement
of every shared word and limb routine with the direct production extraction.
The complete three-layer census checks 124 declarations.

The fourth milestone connects the core native APIs to ordinary integers modulo
both Pasta primes. Define `decode(limbs) = val4(limbs) · R⁻¹ mod p`; Lean checks
the two concrete radix inverses independently of the implementation.

| Native API | Proven result |
| --- | --- |
| `mul`, `square` | Decoded multiplication and squaring modulo `p` |
| `add`, `sub`, `neg`, `double` | Decoded arithmetic modulo `p` |
| `triple`, `mul_by_4`, `mul_by_8` | Decoded scaling modulo `p`, with a stored result below `p` |
| `half` | Decoded division by two for loose and reduced values, preserving the representation bound |
| `mul_add`, `mul_sub` | Decoded composed arithmetic modulo `p` |
| `from_u64`, `from_u128`, `from_i64` | Exact integer embeddings, including the minimum signed input |
| `pow_u64` | Decoded exponentiation for every 64-bit exponent |
| `reduce`, `into_loose` | Canonical stored representative and widening, with decoded value preserved |
| `ZERO`, `ONE`, `is_zero`, `is_one` | Correct identities and zero recognition in the loose representation |
| Montgomery import/access | Limb preservation under the stated representation bound |
| `from_wide_bytes_reduced` | Reduction of every 64-byte little-endian integer modulo `p`, in both representation states |
| `from_bytes_reduced` | Reduction of every finite little-endian byte slice modulo `p`, in both representation states |

The extraction wrapper calls 86 concrete Fp/Fq entry points. The proofs also
cover the explicitly selected private generic halving routine, the reduced
constructor, reduced `from_u64`, already-reduced
`reduce`, and native `square_run` for every count and either factor branch.
Arithmetic and imported loose values assume their documented stored bound
below `2p`; reduced values assume the bound below `p`. These are explicit
proof hypotheses, rather than checks on arbitrary POD bytes.
[NativeBridge.lean](proofs/NativeBridge.lean) connects the actual production
native kernels to the generic harness. Constructors and multiplication use
Common's fast loose multiplier, while the portable addition and subtraction
use its flag-carried modular kernels. The complete census checks 836
declarations, including every supporting native theorem and parameter proof.
Native arithmetic and parity declarations use only Lean's three standard axioms.
Specified codec and unrestricted integer-conversion declarations also retain
Aeneas's abstract `Formatter` type through Rust debug and unwrap signatures.
Each type-only dependency is listed individually in the census catalog.

The root-of-unity APIs cover every 32-bit logarithmic size: sizes above 32
return `None`; accepted sizes return the canonical stored table entry with
primitive order `2^log_size`. The forward value is
`5^((p - 1) / 2^log_size)` modulo the prime. Its inverse has the same primitive
order and their product is one. Loose and reduced Fp/Fq contracts are included.

The default square-root path proves `sqrt`, `sqrt_alt` and `sqrt_ratio` for both
fields and all valid reduced inputs. The contracts distinguish residues and
nonresidues, prove the returned root's equation and stored bound, and cover
zero inputs and zero denominators. The proof checks the fixed exponentiation
chains, primality certificates for both Pasta moduli, the root tables,
Tonelli–Shanks termination and correction invariants, and all six public APIs.
The optional `sqrt-table-large` path covers the same six public APIs and zero
cases. Lean checks the 897 stored powers per field and every inverse-table
lookup used by the order-256 subgroup. The proof follows canonical hash
lookup, four-byte subgroup exponent recovery, table indices and products,
the rounded half exponent, square flags and final reduction. The separately
extracted public callbacks invoke the extracted native exponentiation and
large-table implementations through their four-limb representations.

The 64-byte decoder proves the exact eight-limb iterator sum of its two raw
products, discharges its final zero-carry assertion, and connects REDC to the
independent little-endian integer of the input. The constants and bounds for
both Pasta moduli are checked in Lean.

The arbitrary-length decoder covers empty inputs, zero-padding to 32 or 64 bytes,
and the reverse-chunk Horner loop for longer slices. The proof handles the initial
partial chunk, proves all remaining chunks have 32 bytes, and shows that every
iteration decreases the unconsumed length. Its invariant connects the stored
Montgomery result to the independent little-endian integer of the entire slice.

The deferred `ProductSum` accumulator proves all six public operations for
both fields. Its decoded value is the integer stored by all nine words times
`R⁻²`, reduced modulo the field prime:

| Operation | Proven decoded result |
| --- | --- |
| `new` | Zero |
| `add_product` | Previous value plus the product of the decoded inputs |
| `add_square` | Previous value plus the decoded input squared |
| `add_term` | Previous value plus the decoded input |
| `merge` | Sum of both accumulator values |
| `finish` | The accumulator value, with the returned stored limbs below `2p` |

The contracts cover every nine-word accumulator state and every limb value
of each generic field operand. Partial reduction, the overflow correction,
its seven ADCs and final zero-carry assertion, the sixteen-MAC product chain,
the eight-ADC square and merge chains, and final REDC are included. The bounded
internal product helper also proves exact integer accumulation whenever its
stated `B^9` input bound holds. These contracts place no limit on the number
of public accumulator updates. Slice, array and iterator product sums are
separate paths still being ported. The separately extracted AArch64 Comba helpers
prove exact three-word product-column addition, initialization of four columns
and iterator-based merging of the four column values. Their overflow assertions
are discharged under the stated `B^3` column bound; they are building blocks for
the slice kernel, whose complete public contracts remain pending.

The signed product-difference contracts prove `mul_sub_product` computes
`a*b - c*d` and `mul_sub_double_product` computes `a*b - 2*c*d`, modulo the
selected Pasta prime. They cover both fields and all combinations of loose
and reduced operand states, under each state's documented stored bound.
The result is loose and stored below `2p`. The proofs check all eight doubling
and subtraction words, the outgoing borrow, the selected `p`, `2p` or `3p`
restoration offset, all four corrected upper words, carry cancellation,
optional high-half folding and the final Montgomery reduction.

The signed-62 inversion helpers prove that `to_signed62` preserves every
input digit, `pack62` preserves the represented integer for inputs below
`2^255`, and `unpack62` reverses canonical packing exactly. The packing and
unpacking assertions are included. On the pinned AArch64 target, the
`negative_eta_multiplier` proof covers every odd bottom word and each
low-bit mask of width zero through six: its output is within the mask and
makes `g + f*w` divisible by `2^width`. The proofs connect the actual wrapping
multiplications, subtraction and mask to the integer cancellation identity.
These helpers establish the representation and one accelerated divstep
formula; they do not prove Common's complete inversion routine.

The remaining native paths include inversion. The old Udon inversion proof
does not automatically cover Common's new signed-divsteps implementation.
The optional `aarch64-asm` implementation is outside this package's scope.

The canonical codec proofs cover both loose and reduced values of each field:
integer conversion rejects exactly the inputs at or above the prime; byte
conversion uses the independent little-endian integer of all 32 bytes; and
canonical bytes round-trip exactly. Encoding followed by decoding preserves
the decoded field value. Unrestricted 256-bit integer conversion computes
reduction modulo the prime. Parity reads bit zero of the decoded canonical
representative. Supporting contracts and all public endpoints are included
in the census.

## Standard-library model boundary

Aeneas does not yet supply models for `u64::carrying_add` and
`u64::borrowing_sub`. [word_support/FunsExternal.lean](word_support/FunsExternal.lean)
provides transparent definitions matching the pinned Rust standard-library
bodies: two overflowing operations, a Boolean-to-word conversion, and an OR of
the two flags. [WordPrimitives.lean](proofs/WordPrimitives.lean) proves the exact
integer results and that the flags cannot both be set. The latter discharges
the precondition of Rust's `disjoint_bitor` intrinsic and justifies ordinary
Boolean OR in the models. These are definitions with checked proofs, not
arithmetic axioms. Their agreement with the standard-library bodies is an
explicit translation boundary; the Rust source file is pinned and its hash
is checked during replay.

Common's small multipliers and halving use mutable array iteration and a mutable/owned
Zip rather than an indexed loop. Transparent models implement array
`IntoIterator`, owned iteration in index order, and mutable Zip with Aeneas's
existing `IterMut.next` borrow reconstruction. The source files implementing
these operations and their iterator specializations are pinned during replay.
The model uses value/index state, rather than Rust's pointer and uninitialized
storage representation; its operational agreement with Rust remains an
explicit standard-library translation boundary. These models are used only
for four- and eight-limb, equal-length `u64` iterations in the current native proofs.
Codec models also provide ascending, state-threaded `array::from_fn`,
conditional `bool::then`, `Option` equality, and mutable eight-byte chunks.
The codec proofs check all four callbacks and all four writes. The chunk
model preserves the original full slice and uses an index to represent the
remaining chunks; a returned chunk's writes are reconstructed into that slice.
These proofs use 32-byte slices and eight-byte chunks. Agreement with Rust's storage layout and optimized Zip specialization remains the same explicit
standard-library translation boundary.

Arbitrary-length decoding adds a transparent read-only `Chunks` model. It retains
the unconsumed slice and nonzero chunk size; `next_back` first returns the final
partial chunk, then full chunks. Aeneas's existing `Rev` model supplies reverse
iteration. The pinned Rust sources include the marker, reverse iterator and
iterator trait implementations. [NativeChunks.lean](proofs/NativeChunks.lean)
checks chunk lengths and byte-value decomposition; [NativeBytesLoop.lean](proofs/NativeBytesLoop.lean)
proves the Horner invariant and termination; [NativeBytesCaps.lean](proofs/NativeBytesCaps.lean)
connects it to both fields and representation states.

Aeneas retains the decoder loop's `ReductionState<S>` dictionary but incorrectly
drops its type parameter `S`. [retain_loop_type.py](adapters/retain_loop_type.py)
adds one inert zero-sized `PhantomData<S>::clone` to keep that type in the loop
term, then makes its type argument explicit in Lean. Rust's pinned marker clone
returns the same marker; its transparent model and inertness proof do likewise.
The adapter adds three locals and nine statements, preserves every original
instruction, and requires that reversing the addition restore the entire original
AST. This workaround is an explicit translation boundary.

Aeneas's ordinary `Iterator` dictionary does not carry the backward function
needed by mutable iteration. [model_mutable_iterators.py](adapters/model_mutable_iterators.py)
replaces its mutable dictionary with the transparent model and specializes
exactly ten limb Zip constructors and eighteen limb Zip `next` calls, plus one
byte-chunk constructor and one byte-chunk `next` call. A reverse
comparison checks that all other generated code is identical; immutable Zip
calls are preserved. [NativeSmallLoop.lean](proofs/NativeSmallLoop.lean) proves
that the actual outer loop equals its explicit four-MAC expansion, including
all borrow write-backs. [NativeSmallRepair.lean](proofs/NativeSmallRepair.lean)
proves the four-ADC repair loop, its final carry bound and exact integer sum.
[NativeSmallReduction.lean](proofs/NativeSmallReduction.lean) then proves the
Pasta-specific fold and conditional repair; [NativeSmall.lean](proofs/NativeSmall.lean)
connects it to all six public small-multiplier APIs.
[NativeHalfLoop.lean](proofs/NativeHalfLoop.lean) proves the parity-masked
four-ADC halving loop and borrow reconstruction; [NativeHalf.lean](proofs/NativeHalf.lean)
proves its carry vanishes, its output is even before shifting, and the decoded
result is division by two for both fields and reduction states.
[NativeWideAdd.lean](proofs/NativeWideAdd.lean) proves the eight-ADC loop used
by wide decoding, including every mutable writeback and the exact outgoing carry.

The accumulator's merge loop hits an Aeneas limitation when joining nested
mutable/shared Zip borrows. [unroll_merge.py](adapters/unroll_merge.py) expands
the actual LLBC loop into nine iterations: eight payloads and an exhaustion
check. An independent structural checker compares every copied instruction,
branch and original continuation, verifies that every other declaration and
AST field is unchanged, and rejects four mutations during replay. A false
assertion bounds the expansion. [NativeProductMergeBound.lean](proofs/NativeProductMergeBound.lean)
checks the iterator bound and exhaustion; [NativeProductMergeExpansion.lean](proofs/NativeProductMergeExpansion.lean)
proves the generated merge equals the eight-word ADC composition, discharging
the added guard. [NativeLoopExpansion.lean](proofs/NativeLoopExpansion.lean)
proves that a successful finite loop expansion gives the same result as the
unbounded loop. The adapter's agreement with LLBC control-flow semantics remains
an explicit translation boundary; this is not a verified compiler transformation.
Common's production Rust loop is unchanged. Mutable slice `IntoIterator` uses
the pinned iterator operations and the same transparent borrow reconstruction.

The product-difference loops also contain exhaustion continuations with nested
returns that Aeneas cannot translate. [hoist_product_difference_exits.py](adapters/hoist_product_difference_exits.py)
moves exactly three intact continuations past their loops and leaves a `Break`
in each exhaustion branch. Reversing the movements must restore the complete
original AST; the checker rejects four mutations during replay. Agreement with
LLBC control-flow semantics remains an explicit translation boundary.
[apply_difference_back.py](adapters/apply_difference_back.py) then applies two
generated mutable Zip backward functions to their original iterator seeds.
Its reverse comparison preserves all other generated text.
[NativeProductSubtractLoop.lean](proofs/NativeProductSubtractLoop.lean) proves
all eight resulting writes and the exact subtraction equation;
[NativeProductRestoreLoop.lean](proofs/NativeProductRestoreLoop.lean) proves
the upper-slice restoration and the unchanged lower half. These adapters
preserve production Rust and add no arithmetic axioms.

The square-root extraction also uses a transparent `RangeInclusive::contains`
model matching the pinned Rust range-bound checks, including exhausted ranges.
[copy_bool_assertions.py](adapters/copy_bool_assertions.py) changes only scalar
Boolean assertion operands from `Move` to `Copy`, preserving every assertion
and branch. This avoids Aeneas reading a concrete moved Boolean twice. The
adapter checks exactly two generic and eight native occurrences, reverses the
changes, and requires equality of the entire original AST. An unused cyclic
dictionary back edge is projected while preserving all bodies, types, globals
and exponentiation callbacks. Callback models invoke the extracted native
exponentiation functions whose arithmetic schedules are proved in Lean.

The remaining translation boundary includes Rust/Charon/Aeneas, the supplied
primitive models and Lean's kernel. The axiom census accepts only `propext`,
`Classical.choice` and `Quot.sound`, plus the exact type-only `Formatter`
declaration for specified conversion-multiplier, codec and integer-conversion proofs. This is an abstract
formatting type, not an arithmetic assumption. The per-declaration allowances
are in [catalog.json](catalog.json). The census rejects errors, missing
or duplicate declarations, `sorryAx` and arithmetic axioms. No proof uses
`native_decide`. The extracted model is also scanned for unfilled externals
and proof holes.

## Reproduction

Use the Aeneas release and prepared Lean backend pinned by
[provenance.json](provenance.json). The backend's Lean and Mathlib dependencies
must be installed, along with zsh, Rust `nightly-2026-09-17` and its `rust-src`
component. `AENEAS_TOOL_ROOT` below denotes the unpacked release directory
containing `aeneas`, `charon` and `backends/lean`.

```console
python3 qa/aeneas/build_native_charon.py --archive "$CHARON_SOURCE_ARCHIVE" \
  --output target/aeneas/native-charon --offline
python3 qa/aeneas/reproduce.py --tools "$AENEAS_TOOL_ROOT" \
  --native-charon target/aeneas/native-charon \
  --output target/aeneas/native-check --offline
```

Each run requires a new output directory. It checks the production source,
tool binaries, versions and Rust standard-library source; performs fresh
extraction; compiles every model and proof; and checks the complete census.
The output includes stage commands, exit codes, timings, source/model hashes,
logs and a `results.json` record. `--prepare-only` records
`proofs_checked: false` and makes no proof-validation claim.

The original Git objects and milestone evidence were lost when the previous
checkouts disappeared. This recovery rebuilds the proof sources and extraction
scripts from the recorded edits and regenerates omitted model inputs with the
pinned compiler recipe. The restored package passed fresh extraction, Lean compilation and an exact
axiom census; historical timing records are not reused.

[evidence/fresh.json](evidence/fresh.json) records 40 successful fresh extraction
stages followed by 197 successful model/proof compilation stages after resolving
the dependency cache setup and restoring missing source edits. The earlier setup
failure is retained in the record. All 252 production source hashes, 29 model
hashes and 168 proof source hashes were checked again before saving the evidence.
[evidence/fresh.txt](evidence/fresh.txt) contains the full 836-declaration census.
The policy permits the three standard Lean axioms and exactly 39 named type-only
formatter exceptions; 38 of those exceptions occur in this run. It rejects
arithmetic axioms and `sorryAx`. No proof uses `native_decide`.

The five cumulative layer censuses (13, 40, 124, 256 and 529 declarations) also
pass separately. Their records are in [evidence/layers.json](evidence/layers.json).
Common's complete inversion routine and the complete public slice/iterator
product-sum dispatch remain unproved.
