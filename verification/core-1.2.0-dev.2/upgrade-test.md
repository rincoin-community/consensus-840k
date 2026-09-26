# Upgrade from a running 1.1.0 node, and back

Date: 2026-09-26. Binary: `rincoind` of the release build of commit `5fe6c1272` made by GitHub
Actions (see [`build-manifest.json`](build-manifest.json)), SHA-256
`2f1942cdef9c5f567c57b8abfaefe89e62fe7ac4e9e25e16e761202af430e9c2`.

## What was tested

The data directory of a mainnet node that runs the released Rincoin Community Core `v1.1.0`
(`rincoind` SHA-256 `a3b153b7595145adc938d663e904fba13e9168ad60f3f7d0712abc58874de139`, identical to
the one in the release archive) as a service, with `txindex=1` and the block filter index, was
copied and opened by the 1.2.0 development build. That is the situation of an operator who
upgrades in place.

1. The node was stopped through its service manager, its data directory was copied without the
   wallets, and the node was started again. It was down for 13 seconds and resumed at once.
2. Right before the stop, the running 1.1.0 node reported its best block and its UTXO set.
3. The copy was opened by the 1.2.0 build with the same index options, without any network
   connection (`-connect=0 -listen=0 -dnsseed=0`) and without a wallet.
4. After that, the same copy was opened by the released 1.1.0 again, to see that an operator can
   go back.

## Results

| Check | 1.1.0 before the copy | 1.2.0 on the copy | 1.1.0 again on the copy |
|---|---|---|---|
| Height | 755,293 | 755,293 | 755,293 |
| Best block | `0000000114034810…80dbd0f5f` | same | same |
| UTXO set hash (`hash_serialized_2`) | `c33c5ba6485d19df…c5ae3e1f3` | same | same |
| Coin supply | 19,158,037.5 RIN | same | not queried |
| `txindex` and block filter index | synced | synced to the tip, no rebuild | synced |
| `verifychain 4 5000` | not run | true | not run |
| A transaction looked up by `txindex`, a block filter fetched | not run | both answered | not run |
| Restart | | second start without errors, same UTXO set hash | |
| Errors in `debug.log` | | 0 | 0 |
| Peers connected | | 0 | 0 |

A start takes about two and a half minutes on this data directory, the same for 1.1.0 and 1.2.0;
most of it is loading the block index and the transaction index.

## What this does and does not show

It shows that the 1.2.0 build opens a 1.1.0 data directory as it is, including both indexes,
without a reindex and without changing the chain state, and that 1.1.0 opens the directory again
after 1.2.0 has used it. Below height 840,000 nothing in the chain state depends on the new rules,
so this is the expected result, now measured.

It does not show anything about a wallet: the wallets were left out of the copy on purpose, so that
no test ever touches a real wallet. Opening a real wallet file of 1.1.0 with 1.2.0 was not tested;
wallet behaviour is covered by the functional tests on regtest, which create their wallets fresh.
