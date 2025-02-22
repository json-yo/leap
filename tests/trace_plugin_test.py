#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import unittest
import os

from TestHarness import Cluster, Node, TestHelper, Utils, WalletMgr, CORE_SYMBOL

testSuccessful = True

class TraceApiPluginTest(unittest.TestCase):
    sleep_s = 1
    cluster=Cluster(walletd=True, defproduceraPrvtKey=None)
    walletMgr=WalletMgr(True)
    accounts = []
    cluster.setWalletMgr(walletMgr)

    # kill nodeos and keosd and clean up dir
    def cleanEnv(self, shouldCleanup: bool) :
        self.cluster.killall(allInstances=True)
        if shouldCleanup:
            self.cluster.cleanup()
        self.walletMgr.killall(allInstances=True)
        if shouldCleanup:
            self.walletMgr.cleanup()

    # start keosd and nodeos
    def startEnv(self) :
        account_names = ["alice", "bob", "charlie"]
        abs_path = os.path.abspath(os.getcwd() + '/unittests/contracts/eosio.token/eosio.token.abi')
        traceNodeosArgs = " --trace-rpc-abi eosio.token=" + abs_path
        self.cluster.launch(totalNodes=1, extraNodeosArgs=traceNodeosArgs)
        self.walletMgr.launch()
        testWalletName="testwallet"
        testWallet=self.walletMgr.create(testWalletName, [self.cluster.eosioAccount, self.cluster.defproduceraAccount])
        self.cluster.validateAccounts(None)
        self.accounts=Cluster.createAccountKeys(len(account_names))
        node = self.cluster.getNode(0)
        for idx in range(len(account_names)):
            self.accounts[idx].name =  account_names[idx]
            self.walletMgr.importKey(self.accounts[idx], testWallet)
        for account in self.accounts:
            node.createInitializeAccount(account, self.cluster.eosioAccount, buyRAM=1000000, stakedDeposit=5000000, waitForTransBlock=True, exitOnError=True)
        time.sleep(self.sleep_s)

    def get_block(self, params: str, node: Node) -> json:
        resource = "trace_api"
        command = "get_block"
        payload = {"block_num" : params}
        return node.processUrllibRequest(resource, command, payload)

    def test_TraceApi(self) :
        node = self.cluster.getNode(0)
        for account in self.accounts:
            self.assertIsNotNone(node.verifyAccount(account))

        expectedAmount = Node.currencyIntToStr(5000000, CORE_SYMBOL)
        account_balances = []
        for account in self.accounts:
            amount = node.getAccountEosBalanceStr(account.name)
            self.assertEqual(amount, expectedAmount)
            account_balances.append(amount)

        xferAmount = Node.currencyIntToStr(123456, CORE_SYMBOL)
        trans = node.transferFunds(self.accounts[0], self.accounts[1], xferAmount, "test transfer a->b")
        transId = Node.getTransId(trans)
        blockNum = Node.getTransBlockNum(trans)

        self.assertEqual(node.getAccountEosBalanceStr(self.accounts[0].name), Utils.deduceAmount(expectedAmount, xferAmount))
        self.assertEqual(node.getAccountEosBalanceStr(self.accounts[1].name), Utils.addAmount(expectedAmount, xferAmount))
        time.sleep(self.sleep_s)

        # verify trans via node api before calling trace_api RPC
        blockFromNode = node.getBlock(blockNum)
        self.assertIn("transactions", blockFromNode)
        isTrxInBlockFromNode = False
        for trx in blockFromNode["transactions"]:
            self.assertIn("trx", trx)
            self.assertIn("id", trx["trx"])
            if (trx["trx"]["id"] == transId) :
                isTrxInBlockFromNode = True
                break
        self.assertTrue(isTrxInBlockFromNode)

        # verify trans via trace_api by calling get_block RPC
        blockFromTraceApi = self.get_block(blockNum, node)
        self.assertIn("transactions", blockFromTraceApi["payload"])
        isTrxInBlockFromTraceApi = False
        for trx in blockFromTraceApi["payload"]["transactions"]:
            self.assertIn("id", trx)
            if (trx["id"] == transId) :
                isTrxInBlockFromTraceApi = True
                self.assertIn('actions', trx)
                actions = trx['actions']
                for act in actions:
                    self.assertIn('params', act)
                    prms = act['params']
                    self.assertIn('from', prms)
                    self.assertIn('to', prms)
                    self.assertIn('quantity', prms)
                    self.assertIn('memo', prms)
                break
        self.assertTrue(isTrxInBlockFromTraceApi)
        global testSuccessful
        testSuccessful = True

    @classmethod
    def setUpClass(self):
        self.cleanEnv(self, shouldCleanup=True)
        self.startEnv(self)

    @classmethod
    def tearDownClass(self):
        self.cleanEnv(self, shouldCleanup=testSuccessful)

if __name__ == "__main__":
    unittest.main()
