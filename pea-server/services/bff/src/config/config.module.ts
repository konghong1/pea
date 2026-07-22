import { ConfigModule } from '@nestjs/config';
import configuration from './configuration';

export const ConfigModuleRoot = ConfigModule.forRoot({
  isGlobal: true,
  load: [configuration],
});
