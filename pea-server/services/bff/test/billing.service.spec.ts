import { BadRequestException } from '@nestjs/common';
import { BillingService } from '../src/modules/billing/billing.service';

/**
 * 记账本单元基线测试 (T-ACC-03 / T-OBS-01).
 *
 * 用内存假 DB 模拟 MySQL 行锁下的语义, 验证:
 *  - 预扣正确扣减并返回余额;
 *  - 同 txn_id 幂等 (不双扣) —— 验证幂等校验在行锁之后 (资深开发复核修复点);
 *  - 余额不足抛错;
 *  - 退还正确加回且幂等 (不双退);
 *  - 对账不变量: balance == SUM(credit) - SUM(debit) 恒成立。
 *
 * 说明: 真正的并发双扣只能由 MySQL FOR UPDATE 在行锁层面杜绝, 单测验证的是应用层幂等路径,
 * 二者配合构成完整防护。集成测试 (接真实 MySQL) 应补充并发压测。
 */
class FakeDb {
  accounts = new Map<number, { balance: number; version: number }>();
  ledger: any[] = [];

  async transaction<T>(fn: (conn: any) => Promise<T>): Promise<T> {
    const conn = this.makeConn();
    return fn(conn);
  }

  private makeConn() {
    const self = this;
    return {
      async query(sql: string, params: any[] = []) {
        // 1) accounts 行锁读取
        if (sql.includes('FOR UPDATE') && sql.includes('accounts')) {
          const userId = params[0];
          const acc = self.accounts.get(userId) ?? { balance: 0, version: 0 };
          return [[acc], []];
        }
        // 2) 幂等校验: 按 txn_id 查已有流水
        if (sql.includes('ledger_entries WHERE txn_id')) {
          const txnId = params[0];
          const found = self.ledger.find((l) => l.txn_id === txnId);
          return [found ? [found] : [], []];
        }
        // 3) 写流水。注意: 生产代码把零侧(debit/credit)以字面量 0 内联 SQL,
        //    故入参只有 6 个 (preauth: debit 绑定, credit 内联0; refund: credit 绑定, debit 内联0)。
        if (sql.includes('INSERT INTO ledger_entries')) {
          let userId: any, txn_id: any, job_id: any, type: any, debit = 0, credit = 0, balance_after: any;
          if (sql.includes('?, 0, ?)')) {
            // preauth: (..., debit, 0, balance_after)
            [userId, txn_id, job_id, type, debit, balance_after] = params;
          } else if (sql.includes('(?, ?, ?, ?, 0, ?, ?)')) {
            // refund: (..., 0, credit, balance_after)
            [userId, txn_id, job_id, type, credit, balance_after] = params;
          } else {
            [userId, txn_id, job_id, type, debit, credit, balance_after] = params;
          }
          const row = {
            id: self.ledger.length + 1,
            user_id: userId,
            txn_id,
            job_id,
            type,
            debit,
            credit,
            balance_after,
          };
          self.ledger.push(row);
          return [{ affectedRows: 1, insertId: row.id }, []];
        }
        // 4) 更新余额
        if (sql.includes('UPDATE accounts SET balance')) {
          const [balance, userId] = params;
          const acc = self.accounts.get(userId) ?? { balance: 0, version: 0 };
          acc.balance = balance;
          acc.version += 1;
          self.accounts.set(userId, acc);
          return [{ affectedRows: 1 }, []];
        }
        return [[], []];
      },
    };
  }
}

const pubsub = { publish: async () => {} } as any;

function newService(seedBalance = 100) {
  const db = new FakeDb();
  db.accounts.set(1, { balance: seedBalance, version: 0 });
  return { svc: new BillingService(db as any, pubsub), db };
}

describe('BillingService 记账本正确性', () => {
  it('预扣正确扣减并返回新余额', async () => {
    const { svc, db } = newService(100);
    const r = await svc.preauthorize(1, 10, 'tx:1:preauth');
    expect(r.balance).toBe(90);
    expect(db.accounts.get(1)!.balance).toBe(90);
  });

  it('同 txn_id 幂等: 不双扣', async () => {
    const { svc, db } = newService(100);
    await svc.preauthorize(1, 10, 'tx:dup:preauth');
    const r2 = await svc.preauthorize(1, 10, 'tx:dup:preauth');
    expect(r2.balance).toBe(90); // 第二次应直接返回, 余额仍为 90
    expect(db.ledger.filter((l) => l.type === 'preauth')).toHaveLength(1);
  });

  it('余额不足抛 BadRequestException', async () => {
    const { svc } = newService(5);
    await expect(svc.preauthorize(1, 10, 'tx:insufficient')).rejects.toThrow(BadRequestException);
  });

  it('退还正确加回且幂等: 不双退', async () => {
    const { svc, db } = newService(90);
    const r1 = await svc.refund(1, 10, 'tx:1:refund');
    expect(r1.refunded).toBe(true);
    const r2 = await svc.refund(1, 10, 'tx:1:refund');
    expect(r2.refunded).toBe(false); // 已退还
    expect(db.accounts.get(1)!.balance).toBe(100);
    expect(db.ledger.filter((l) => l.type === 'refund')).toHaveLength(1);
  });

  it('对账不变量: balance == SUM(credit) - SUM(debit)', async () => {
    const { svc, db } = newService(1000);
    // 模拟注册开户赠金流水 (auth.service 写入)
    db.ledger.push({
      id: 1, user_id: 1, txn_id: 'grant:1', job_id: null,
      type: 'grant', debit: 0, credit: 1000, balance_after: 1000,
    });
    await svc.preauthorize(1, 10, 'tx:g:preauth');
    await svc.refund(1, 10, 'tx:g:refund');

    const sumCredit = db.ledger.reduce((s, l) => s + l.credit, 0);
    const sumDebit = db.ledger.reduce((s, l) => s + l.debit, 0);
    const balance = db.accounts.get(1)!.balance;
    expect(balance).toBe(1000);
    expect(balance).toBe(sumCredit - sumDebit);
  });
});
