"""Offline assumptions: defaults are illustrative, never broker fee estimates."""
from dataclasses import asdict, dataclass, field
from pathlib import Path
import tomllib
from .data import finite


@dataclass(frozen=True)
class Costs:
    commission_per_share: float = .005
    minimum_commission: float = 1.0
    fee_bps: float = .1
    spread_bps: float = 2.0
    slippage_bps: float = 1.0
    impact_bps: float = 10.0

    def __post_init__(self):
        for name, value in asdict(self).items():
            finite(value, name)

    def execution(self, reference: float, quantity: int, volume: int) -> tuple[float, float]:
        finite(reference, 'reference', 1e-12)
        if not quantity or volume <= 0:
            raise ValueError('nonzero quantity and positive volume required')
        participation = abs(quantity) / volume
        adverse_bps = self.spread_bps / 2 + self.slippage_bps + self.impact_bps * participation**.5
        price = reference * (1 + (1 if quantity > 0 else -1) * adverse_bps / 10000)
        finite(price, 'execution price', 1e-12)
        fee = max(self.minimum_commission, abs(quantity) * self.commission_per_share)
        fee += abs(quantity) * price * self.fee_bps / 10000
        return price, finite(fee, 'fee')


@dataclass(frozen=True)
class Limits:
    max_order_quantity: int = 1000
    max_symbol_notional: float = 20000
    max_gross_notional: float = 50000
    max_net_notional: float = 50000
    max_sector_notional: float = 30000
    max_daily_loss_fraction: float = .02
    max_drawdown_fraction: float = .05
    max_price_jump_fraction: float = .10
    max_participation: float = .10
    max_mark_age_seconds: int = 120

    def __post_init__(self):
        for name, value in asdict(self).items():
            finite(value, name, 1e-12)
            if 'fraction' in name or name == 'max_participation':
                if value > 1:
                    raise ValueError(f'{name} must be <= 1')
        if type(self.max_order_quantity) is not int or type(self.max_mark_age_seconds) is not int:
            raise ValueError('order quantity and mark age must be integers')


@dataclass(frozen=True)
class Config:
    mode: str = 'simulation'
    initial_cash: float = 100000
    interval_seconds: int = 60
    costs: Costs = field(default_factory=Costs)
    limits: Limits = field(default_factory=Limits)
    sectors: dict[str, str] = field(default_factory=lambda: {'DEMO': 'synthetic'})
    fast_window: int = 5
    slow_window: int = 20
    target_quantity: int = 100

    def __post_init__(self):
        if self.mode != 'simulation':
            raise ValueError('only offline simulation mode is supported; broker modes are unavailable')
        finite(self.initial_cash, 'initial_cash', 1e-12)
        for name in ('interval_seconds', 'fast_window', 'slow_window', 'target_quantity'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'{name} must be a positive integer')
        if self.fast_window >= self.slow_window:
            raise ValueError('fast_window must be less than slow_window')
        if not self.sectors or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v
                                   for k, v in self.sectors.items()):
            raise ValueError('sectors must map nonempty symbols to sector names')

    @classmethod
    def load(cls, path: Path):
        with Path(path).open('rb') as stream:
            values = tomllib.load(stream)
        values['costs'] = Costs(**values.pop('costs', {}))
        values['limits'] = Limits(**values.pop('limits', {}))
        return cls(**values)
