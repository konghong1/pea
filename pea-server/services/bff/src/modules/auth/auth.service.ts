import {
  Injectable,
  ConflictException,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { ConfigService } from '@nestjs/config';
import * as bcrypt from 'bcryptjs';
import { DatabaseService } from '../../database/database.service';
import { RegisterDto, LoginDto } from './auth.dto';

export interface AuthUser {
  id: number;
  email: string;
  displayName: string;
}

@Injectable()
export class AuthService {
  constructor(
    private readonly db: DatabaseService,
    private readonly jwt: JwtService,
    private readonly config: ConfigService,
  ) {}

  async register(dto: RegisterDto): Promise<{ user: AuthUser; token: string }> {
    const exists = await this.db.query<any[]>(
      'SELECT id FROM users WHERE email = ?',
      [dto.email],
    );
    if (exists.length) throw new ConflictException('email already registered');

    const hash = await bcrypt.hash(dto.password, 10);
    const free = this.config.get<number>('freeTapies') ?? 1000;

    const result = await this.db.transaction(async (conn) => {
      const [u] = await conn.query(
        'INSERT INTO users (email, password_hash, display_name) VALUES (?, ?, ?)',
        [dto.email, hash, dto.displayName ?? ''],
      );
      const userId = (u as any).insertId;
      await conn.query(
        'INSERT INTO accounts (user_id, balance, version) VALUES (?, ?, 0)',
        [userId, free],
      );
      // 写开户赠金流水 (贷方), 作为余额对账基准: balance == SUM(credit) - SUM(debit)
      // 缺此行则余额与流水永远对不上 (资深开发复核 T-ACC-03)。
      // 注意: ledger_entries.type 枚举需含 'grant' (见 infra/mysql/init/01-schema.sql)。
      await conn.query(
        `INSERT INTO ledger_entries (user_id, txn_id, job_id, type, debit, credit, balance_after)
         VALUES (?, ?, NULL, 'grant', 0, ?, ?)`,
        [userId, `grant:${userId}`, free, free],
      );
      return userId;
    });

    return { user: this.toUser(result, dto.email, dto.displayName ?? ''), token: this.sign(result, dto.email) };
  }

  async login(dto: LoginDto): Promise<{ user: AuthUser; token: string }> {
    const rows = await this.db.query<any[]>(
      'SELECT id, email, display_name, password_hash FROM users WHERE email = ?',
      [dto.email],
    );
    const user = rows[0];
    if (!user) throw new UnauthorizedException('invalid credentials');
    const ok = await bcrypt.compare(dto.password, user.password_hash);
    if (!ok) throw new UnauthorizedException('invalid credentials');
    return {
      user: this.toUser(user.id, user.email, user.display_name),
      token: this.sign(user.id, user.email),
    };
  }

  private sign(sub: number, email: string): string {
    return this.jwt.sign(
      { sub, email },
      { secret: this.config.get('jwt.secret'), expiresIn: this.config.get('jwt.expiresIn') },
    );
  }

  private toUser(id: number, email: string, displayName: string): AuthUser {
    return { id, email, displayName };
  }
}
