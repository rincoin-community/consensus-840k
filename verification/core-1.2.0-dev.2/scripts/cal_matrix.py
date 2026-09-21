#!/usr/bin/env python3
"""Cross-implementation acceptance matrix on regtest.

Three real node implementations run side by side on a private regtest chain:

  C  Rincoin Community Core 1.2.0 (development build)
  A  Rin-coin/rincoin v1.1.0-rc1
  L  Rin-coin/rincoin v1.0.5 (the legacy schedule)

Blocks are mined by each implementation's own miner (full reward, as its
getblocktemplate would offer it) and handed to the others with submitblock, so
every accept/reject verdict and reason comes from the validating node itself.
Transactions are made by each implementation's own wallet and offered to the
others' mempools (policy and consensus) and, separately, put into a block that the
validating node assembles itself with generateblock (consensus only).

Nothing here touches a public network: regtest only, isolated datadirs and ports,
-dnsseed=0, nodes are only ever connected to each other.
"""

import argparse
import json
import os
import shutil
import sys
import time

p = argparse.ArgumentParser()
p.add_argument("--framework", required=True, help="test/functional directory that provides test_framework")
p.add_argument("--workdir", required=True)
p.add_argument("--out", required=True, help="result file (JSON)")
p.add_argument("--c-bin", required=True)
p.add_argument("--a-bin", required=True)
p.add_argument("--l-bin", required=True)
p.add_argument("--cli", required=True)
p.add_argument("--label", default="")
args = p.parse_args()

sys.path.insert(0, args.framework)
from test_framework.address import ADDRESS_BCRT1_UNSPENDABLE  # noqa: E402
from test_framework.authproxy import JSONRPCException  # noqa: E402
from test_framework.blocktools import create_block, create_coinbase  # noqa: E402
from test_framework.test_node import TestNode  # noqa: E402
from test_framework.util import PortSeed, initialize_datadir  # noqa: E402

PortSeed.n = os.getpid()

FORK = 840                 # transition height on regtest in all three (4 x 210)
COMMON_TIP = 835           # the shared pre-transition state every scenario starts from
NEUTRAL = ADDRESS_BCRT1_UNSPENDABLE
COIN = 100000000
# MWEB: C activates it by height (start 2,160) on regtest, A and L by time (active from 432). Aligned at
# run time with the regtest-only -vbparams option so that no chain in this test carries MWEB data.
MWEB_ALIGN = "-vbparams=mweb:0:0:2160:2304"
IMPLS = {
    "C": {"index": 0, "bin": args.c_bin, "extra": []},
    "A": {"index": 1, "bin": args.a_bin, "extra": [MWEB_ALIGN]},
    "L": {"index": 2, "bin": args.l_bin, "extra": [MWEB_ALIGN]},
}
ORDER = ["C", "A", "L"]

results = {"label": args.label, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "implementations": {},
           "records": [], "notes": []}


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def record(scenario, step, **kw):
    entry = {"scenario": scenario, "step": step}
    entry.update(kw)
    results["records"].append(entry)
    shown = {k: v for k, v in kw.items() if k not in ("detail",)}
    log("  [%s] %s: %s" % (scenario, step, json.dumps(shown, default=str)))


class Net:
    """One node per implementation, started from a copy of a snapshot (or from nothing)."""

    def __init__(self, name, snapshot=None):
        self.dir = os.path.join(args.workdir, name)
        if os.path.exists(self.dir):
            shutil.rmtree(self.dir)
        os.makedirs(self.dir)
        self.nodes = {}
        for impl in ORDER:
            cfg = IMPLS[impl]
            if snapshot:
                datadir = os.path.join(self.dir, "node%d" % cfg["index"])
                shutil.copytree(os.path.join(args.workdir, snapshot, "node%d" % cfg["index"]), datadir)
            else:
                datadir = initialize_datadir(self.dir, cfg["index"], "regtest")
            node = TestNode(cfg["index"], datadir, chain="regtest", rpchost=None, timewait=120, timeout_factor=1.0,
                            bitcoind=cfg["bin"], bitcoin_cli=args.cli, coverage_dir=None, cwd=self.dir,
                            extra_args=["-par=1", "-bind=127.0.0.1"] + cfg["extra"])
            self.nodes[impl] = node
        for node in self.nodes.values():
            node.start()
        for node in self.nodes.values():
            node.wait_for_rpc_connection()
        if not snapshot:
            for node in self.nodes.values():
                node.createwallet(wallet_name="", load_on_startup=True)

    def __getitem__(self, impl):
        return self.nodes[impl]

    def stop(self):
        for node in self.nodes.values():
            if node.running:
                node.stop_node()
        for node in self.nodes.values():
            node.wait_until_stopped()


def block_facts(node, block_hash):
    b = node.getblock(block_hash, 2)
    cb = b["tx"][0]
    return {"height": b["height"], "hash": block_hash, "version": b["versionHex"], "ntx": len(b["tx"]),
            "coinbase_value": int(round(sum(float(o["value"]) for o in cb["vout"]) * COIN)),
            "coinbase_scriptsig": cb["vin"][0]["coinbase"]}


def offer_block(validator, raw_hex):
    """submitblock: (verdict, reason). 'inconclusive' means valid but not (yet) the best chain."""
    res = validator.submitblock(raw_hex)
    if res is None:
        return "accepted", None
    if res in ("duplicate", "inconclusive"):
        return "accepted", res
    return "rejected", res


def feed(scenario, step, producer_impl, producer, validator_impl, validator, hashes, note=None):
    """Hand the producer's blocks to the validator in order; record each verdict."""
    out = []
    for h in hashes:
        facts = block_facts(producer, h)
        verdict, reason = offer_block(validator, producer.getblock(h, 0))
        on_best = validator.getbestblockhash() == h
        record(scenario, step, kind="block", producer=producer_impl, validator=validator_impl, height=facts["height"],
               version=facts["version"], coinbase_value=facts["coinbase_value"], ntx=facts["ntx"], verdict=verdict,
               reason=reason, became_tip=on_best, note=note)
        out.append((verdict, reason))
    return out


def own_tx(node, amount=1):
    """An ordinary wallet payment of this implementation, to an address outside every wallet."""
    txid = node.sendtoaddress(NEUTRAL, amount)
    return txid, node.gettransaction(txid)["hex"]


def judge_tx(scenario, step, producer_impl, validator_impl, validator, raw_hex, note=None):
    """Mempool verdict (policy + consensus) and block verdict (consensus only) of one validator."""
    if producer_impl == validator_impl:
        # the producer's wallet has already put it into the producer's own mempool
        record(scenario, step, kind="tx-mempool", producer=producer_impl, validator=validator_impl, verdict="accepted",
               reason=None, note="own mempool (accepted when the wallet sent it)")
    else:
        mp = validator.testmempoolaccept([raw_hex])[0]
        record(scenario, step, kind="tx-mempool", producer=producer_impl, validator=validator_impl,
               verdict="accepted" if mp["allowed"] else "rejected", reason=mp.get("reject-reason"), note=note)
    tip = validator.getbestblockhash()
    try:
        res = validator.generateblock(NEUTRAL, [raw_hex])
        verdict, reason = "accepted", None
        # leave the validator where it was
        validator.invalidateblock(res["hash"])
        assert validator.getbestblockhash() == tip
    except JSONRPCException as e:
        verdict, reason = "rejected", e.error["message"]
    record(scenario, step, kind="tx-block", producer=producer_impl, validator=validator_impl, verdict=verdict,
           reason=reason, note=note)


# ------------------------------------------------------------------------------------------------
# Common pre-transition state
# ------------------------------------------------------------------------------------------------

def build_common():
    log("Building the common pre-transition state (tip %d), mined by L" % COMMON_TIP)
    net = Net("common")
    for impl in ORDER:
        info = net[impl].getnetworkinfo()
        results["implementations"][impl] = {"binary": IMPLS[impl]["bin"], "subversion": info["subversion"],
                                            "protocolversion": info["protocolversion"],
                                            "genesis": net[impl].getblockhash(0), "extra_args": IMPLS[impl]["extra"]}
    assert len({v["genesis"] for v in results["implementations"].values()}) == 1, "genesis blocks differ"
    addr = {impl: net[impl].getnewaddress() for impl in ORDER}
    miner = net["L"]
    plan = [(addr["C"], 100), (addr["A"], 100), (addr["L"], 100), (NEUTRAL, COMMON_TIP - 300)]
    for a, n in plan:
        hashes = miner.generatetoaddress(n, a)
        for h in hashes:
            raw = miner.getblock(h, 0)
            for impl in ("C", "A"):
                res = net[impl].submitblock(raw)
                assert res is None, "%s rejected common block %s: %s" % (impl, h, res)
    tips = {impl: net[impl].getbestblockhash() for impl in ORDER}
    assert len(set(tips.values())) == 1 and net["C"].getblockcount() == COMMON_TIP
    record("1", "common state", kind="state", height=COMMON_TIP, tip=tips["C"], mined_by="L",
           accepted_by=["C", "A", "L"], note="835 blocks mined by L and accepted by C and A through submitblock")
    for impl in ORDER:
        bal = net[impl].getbalance()
        assert bal > 1000, (impl, bal)
    net.stop()
    # the snapshot is the stopped common directory itself
    return "common"


# ------------------------------------------------------------------------------------------------
# Scenarios
# ------------------------------------------------------------------------------------------------

def scenario_1_and_2_and_3(snapshot):
    """1: each implementation crosses its own boundary. 2: empty activation blocks against every validator,
    and the whole history after them. 3: the first ordinary transaction of each implementation, on its own
    branch, ancestors included. One producer at a time; validators always start from the common state."""
    for prod in ORDER:
        log("Producer %s: own branch across the transition height" % prod)
        net = Net("s123_%s" % prod, snapshot)
        node = net[prod]
        # below the transition height
        pre = node.generatetoaddress(FORK - 1 - COMMON_TIP, NEUTRAL)       # 836..839
        first = node.generatetoaddress(1, NEUTRAL)                        # 840, empty
        empty_after = node.generatetoaddress(2, NEUTRAL)                  # 841, 842, empty
        txid, raw_tx = own_tx(node)
        with_tx = node.generatetoaddress(1, NEUTRAL)                      # 843, first ordinary transaction
        assert txid in node.getblock(with_tx[0])["tx"]
        tail = node.generatetoaddress(2, NEUTRAL)                         # 844, 845
        for h in pre[-1:] + first + empty_after[:1] + with_tx:
            f = block_facts(node, h)
            record("1", "own chain of %s" % prod, kind="own-block", producer=prod, **f)
        for val in ORDER:
            if val == prod:
                continue
            v = net[val]
            feed("1", "blocks below the transition height", prod, node, val, v, pre)
            feed("2", "first block at the transition height (empty)", prod, node, val, v, first)
            feed("2", "empty blocks after it", prod, node, val, v, empty_after)
            feed("3", "block with the producer's first ordinary transaction", prod, node, val, v, with_tx)
            feed("3", "blocks after it", prod, node, val, v, tail)
            record("2", "validator's tip after the producer's whole history", kind="state", producer=prod, validator=val,
                   height=v.getblockcount(), follows_producer=v.getbestblockhash() == node.getbestblockhash())
        net.stop()


def scenario_tx_matrix(snapshot):
    """3 and 8: transactions judged on their own, apart from the blocks that carry them. Every validator is on
    its own valid chain at the same height as the producer when it judges the transaction."""
    for stage, target in (("below the transition height", COMMON_TIP + 2), ("above the transition height", FORK + 2)):
        for prod in ORDER:
            net = Net("tx_%s_%d" % (prod, target), snapshot)
            for impl in ORDER:
                net[impl].generatetoaddress(target - COMMON_TIP, NEUTRAL)
                assert net[impl].getblockcount() == target
            txid, raw_tx = own_tx(net[prod])
            for val in ORDER:
                judge_tx("8" if {prod, val} == {"A", "L"} else "3", "ordinary wallet transaction, signed %s" % stage,
                         prod, val, net[val], raw_tx,
                         note="validator on its own chain at height %d" % target)
            net.stop()


def scenario_4(snapshot):
    """A transaction of A on A's short branch; a stronger empty history by C that A still recognizes."""
    net = Net("s4", snapshot)
    a, c = net["A"], net["C"]
    txid, raw_tx = own_tx(a)
    a.generatetoaddress(1, NEUTRAL)                                       # 836a with the transaction
    assert a.gettransaction(txid)["confirmations"] == 1
    c_branch = c.generatetoaddress(3, NEUTRAL)                            # 836c..838c, empty, below the transition
    out = feed("4", "stronger empty C history below the transition height, offered to A", "C", c, "A", a, c_branch)
    conf = a.gettransaction(txid)["confirmations"]
    record("4", "A after the reorganization", kind="state", validator="A", height=a.getblockcount(),
           follows_c=a.getbestblockhash() == c.getbestblockhash(), tx_confirmations=conf,
           tx_back_in_mempool=txid in a.getrawmempool(),
           note="expected: reorganization, the transaction loses its confirmation and waits in the mempool")
    # the same attempt across the transition height
    c_more = c.generatetoaddress(FORK + 2 - c.getblockcount(), NEUTRAL)   # 839c..842c
    feed("4", "the C history continued across the transition height, offered to A", "C", c, "A", a, c_more)
    record("4", "A at the end", kind="state", validator="A", height=a.getblockcount(),
           follows_c=a.getbestblockhash() == c.getbestblockhash())
    net.stop()
    return out


def scenario_5(snapshot):
    """A transaction of C on C's branch above the transition height; a stronger empty history by A."""
    net = Net("s5", snapshot)
    a, c = net["A"], net["C"]
    shared = a.generatetoaddress(FORK - 1 - COMMON_TIP, NEUTRAL)          # 836..839 by A, valid for everybody
    feed("5", "shared blocks below the transition height (mined by A)", "A", a, "C", c, shared)
    c_first = c.generatetoaddress(1, NEUTRAL)                             # 840c
    txid, raw_tx = own_tx(c)
    c_tx_block = c.generatetoaddress(1, NEUTRAL)                          # 841c with the C transaction
    assert c.gettransaction(txid)["confirmations"] == 1
    a_branch = a.generatetoaddress(4, NEUTRAL)                            # 840a..843a, empty
    feed("5", "stronger empty A history across the transition height, offered to C", "A", a, "C", c, a_branch)
    record("5", "C after the offer", kind="state", validator="C", height=c.getblockcount(),
           follows_a=c.getbestblockhash() == a.getbestblockhash(),
           tx_confirmations=c.gettransaction(txid)["confirmations"], tx_back_in_mempool=txid in c.getrawmempool(),
           note="the signature rule is not a checkpoint: an empty branch with more work is followed")
    # C continues on top of A's branch with its transaction; A judges that block
    c_next = c.generatetoaddress(1, NEUTRAL)
    record("5", "C mines on top, confirming its transaction again", kind="own-block", producer="C",
           **block_facts(c, c_next[0]))
    feed("5", "C's block on top of A's branch, offered to A", "C", c, "A", a, c_next)
    del c_first, c_tx_block
    net.stop()


def scenario_6_and_7(snapshot):
    """6: L mines the block at the transition height with its own (previous-schedule) subsidy; A and C judge it,
    A then tries to build on it. 7: empty descendants of a block a validator considers invalid."""
    net = Net("s67", snapshot)
    l, a, c = net["L"], net["A"], net["C"]
    shared = l.generatetoaddress(FORK - 1 - COMMON_TIP, NEUTRAL)
    for val in ("A", "C"):
        feed("6", "shared blocks below the transition height (mined by L)", "L", l, val, net[val], shared)
    l_first = l.generatetoaddress(1, NEUTRAL)                             # 840L: 3.125 RIN
    record("6", "L's block at the transition height", kind="own-block", producer="L", **block_facts(l, l_first[0]))
    verdict_a = feed("6", "L's block at the transition height", "L", l, "A", a, l_first)[0]
    verdict_c = feed("6", "L's block at the transition height", "L", l, "C", c, l_first)[0]
    # A's next block, wherever A stands now
    a_next = a.generatetoaddress(1, NEUTRAL)
    fa = block_facts(a, a_next[0])
    record("6", "A's next block", kind="own-block", producer="A", builds_on_l=a.getblock(a_next[0])["previousblockhash"] == l_first[0], **fa)
    feed("6", "A's next block, offered to C", "A", a, "C", c, a_next)
    feed("6", "A's next block, offered to L", "A", a, "L", l, a_next)

    # 7: empty descendants of L's block, with more work than C's own chain
    l_more = l.generatetoaddress(6, NEUTRAL)                              # 841L..846L, empty
    c_own = c.generatetoaddress(2, NEUTRAL)                               # two blocks of C's own, fewer than L has
    tip = c.getbestblockhash()
    feed("7", "empty descendants of the block C rejected (6 blocks, more than C's own chain)", "L", l, "C", c, l_more)
    record("7", "C afterwards", kind="state", validator="C", height=c.getblockcount(), kept_own_tip=c.getbestblockhash() == tip)
    # a hand-built empty child that satisfies every rule of C on its own
    parent = l.getblock(l_first[0])
    child = create_block(int(parent["hash"], 16), create_coinbase(FORK + 1), parent["time"] + 1, version=0x20000000)
    child.solve()
    v, r = offer_block(c, child.serialize().hex())
    record("7", "hand-built empty child of the rejected block (4 RIN, valid on its own)", kind="block", producer="test",
           validator="C", height=FORK + 1, version="20000000", coinbase_value=4 * COIN, ntx=1, verdict=v, reason=r,
           became_tip=c.getbestblockhash() == child.hash)
    del verdict_a, verdict_c, c_own
    net.stop()


def scenario_negative_blocks(snapshot):
    """Manipulated boundary blocks, built by the test (not by any implementation's miner)."""
    net = Net("neg", snapshot)
    l = net["L"]
    l.generatetoaddress(FORK - 1 - COMMON_TIP, NEUTRAL)
    shared = [l.getblockhash(h) for h in range(COMMON_TIP + 1, FORK)]
    for impl in ("C", "A"):
        for h in shared:
            assert net[impl].submitblock(l.getblock(h, 0)) is None
    parent = l.getblock(l.getbestblockhash())
    variants = [
        ("4 RIN, ordinary version", 4 * COIN, 0x20000000),
        ("4 RIN, version 0x52494e33", 4 * COIN, 0x52494e33),
        ("3.125 RIN, ordinary version", 312500000, 0x20000000),
        ("3.125 RIN, version 0x52494e33", 312500000, 0x52494e33),
        ("4 RIN less one base unit, ordinary version", 4 * COIN - 1, 0x20000000),
        ("4 RIN plus one base unit, ordinary version", 4 * COIN + 1, 0x20000000),
        ("6.25 RIN (no change at all), ordinary version", 625000000, 0x20000000),
    ]
    for description, value, version in variants:
        cb = create_coinbase(FORK)
        cb.vout[0].nValue = value
        cb.rehash()
        block = create_block(int(parent["hash"], 16), cb, parent["time"] + 1, version=version)
        block.solve()
        raw = block.serialize().hex()
        for val in ORDER:
            v, r = offer_block(net[val], raw)
            record("negative", "hand-built empty block at the transition height: " + description, kind="block",
                   producer="test", validator=val, height=FORK, version="%08x" % version, coinbase_value=value,
                   verdict=v, reason=r)
            if v == "accepted" and net[val].getbestblockhash() == block.hash:
                net[val].invalidateblock(block.hash)
    net.stop()


def scenario_p2p(snapshot):
    """Which pairs of implementations keep a P2P connection, below and above the transition height."""
    from test_framework.util import p2p_port
    for stage, target in (("below the transition height", COMMON_TIP + 1), ("above the transition height", FORK + 1)):
        net = Net("p2p_%d" % target, snapshot)
        for impl in ORDER:
            net[impl].generatetoaddress(target - COMMON_TIP, NEUTRAL)
        for x in ORDER:
            for y in ORDER:
                if x == y:
                    continue
                nx = net[x]
                nx.addnode("127.0.0.1:%d" % p2p_port(IMPLS[y]["index"]), "onetry")
                time.sleep(4)
                peers = [pi for pi in nx.getpeerinfo() if not pi["inbound"]]
                kept = len(peers) == 1
                info = {"version": peers[0]["version"], "subver": peers[0]["subver"], "services": peers[0]["servicesnames"]} if kept else None
                record("p2p", "manual outbound connection %s, each node on its own chain at height %d" % (stage, target),
                       kind="p2p", source=x, target=y, kept=kept, peer=info)
                for pi in nx.getpeerinfo():
                    nx.disconnectnode(nodeid=pi["id"])
                time.sleep(1)
        net.stop()


def main():
    os.makedirs(args.workdir, exist_ok=True)
    snapshot = build_common()
    scenario_1_and_2_and_3(snapshot)
    scenario_tx_matrix(snapshot)
    scenario_4(snapshot)
    scenario_5(snapshot)
    scenario_6_and_7(snapshot)
    scenario_negative_blocks(snapshot)
    scenario_p2p(snapshot)
    results["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with open(args.out, "w", encoding="utf8") as f:
        json.dump(results, f, indent=1, default=str)
    log("Wrote %s (%d records)" % (args.out, len(results["records"])))


if __name__ == "__main__":
    main()
