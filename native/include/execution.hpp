#pragma once
#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <limits>
#include <map>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

namespace offline {
using Quantity = std::int64_t;
using Time = std::int64_t; // Monotonic replay nanoseconds, nonnegative.
inline bool positive(double x) { return std::isfinite(x) && x>0; }
inline bool nonnegative(double x) { return std::isfinite(x) && x>=0; }

template<class T, std::size_t Capacity> class SpscQueue {
 static_assert(Capacity>0 && (Capacity & (Capacity-1))==0 && Capacity < (std::uint64_t{1}<<63));
 static_assert(std::is_trivially_copyable_v<T>);
 std::array<T,Capacity> data_{};
 alignas(64) std::atomic<std::uint64_t> head_{0};
 alignas(64) std::atomic<std::uint64_t> tail_{0};
 std::atomic<std::uint64_t> overflows_{0};
public:
 bool push(const T& value) noexcept {
  auto head=head_.load(std::memory_order_relaxed);
  if(head-tail_.load(std::memory_order_acquire)>=Capacity) {overflows_.fetch_add(1,std::memory_order_relaxed); return false;}
  data_[head%Capacity]=value; head_.store(head+1,std::memory_order_release); return true;
 }
 bool pop(T& value) noexcept {
  auto tail=tail_.load(std::memory_order_relaxed);
  if(tail==head_.load(std::memory_order_acquire)) return false;
  value=data_[tail%Capacity]; tail_.store(tail+1,std::memory_order_release); return true;
 }
 std::uint64_t overflows() const noexcept {return overflows_.load(std::memory_order_relaxed);}
};

// Continuous linear temporary impact AC trajectory sampled at equal time boundaries.
inline std::vector<Quantity> schedule(Quantity total, std::size_t slices, double horizon_seconds,
 double risk_aversion, double sigma, double eta) {
 if(total<=0 || total>1'000'000'000'000LL || slices==0 || slices>1'000'000 ||
 !positive(horizon_seconds)||!nonnegative(risk_aversion)||!nonnegative(sigma)||!positive(eta))
  throw std::invalid_argument("invalid schedule inputs");
 long double z=0;
 if(risk_aversion>0 && sigma>0) z=std::exp(0.5L*(std::log(static_cast<long double>(risk_aversion))-std::log(static_cast<long double>(eta)))+std::log(static_cast<long double>(sigma))+std::log(static_cast<long double>(horizon_seconds)));
 std::vector<Quantity> result; result.reserve(slices); Quantity previous=total;
 for(std::size_t i=1;i<=slices;++i) {
  const long double fraction=static_cast<long double>(i)/slices;
  long double remaining=0;
  if(i<slices) {
   if(z<1e-7L) remaining=1-fraction;
   else if(!std::isfinite(z)) remaining=0;
   else remaining=std::exp(-z*fraction)*(-std::expm1(-2*z*(1-fraction)))/(-std::expm1(-2*z));
  }
  Quantity next=std::clamp(static_cast<Quantity>(std::llround(total*remaining)),Quantity{0},previous);
  result.push_back(previous-next); previous=next;
 }
 return result;
}

class TokenBucket {
 double capacity_, rate_, tokens_; Time previous_;
public:
 TokenBucket(double capacity, double per_second, Time start):capacity_(capacity),rate_(per_second),tokens_(capacity),previous_(start) {
  if(!positive(capacity)||capacity<1||capacity>1'000'000'000||!positive(per_second)||start<0) throw std::invalid_argument("invalid token bucket");
 }
 bool take(Time now) {
  if(now<previous_) return false;
  const long double refill=static_cast<long double>(now-previous_)*rate_/1e9L;
  tokens_=static_cast<double>(std::min(static_cast<long double>(capacity_),tokens_+refill)); previous_=now;
  if(tokens_<1) return false;
  tokens_-=1; return true;
 }
};

enum class State { BOOT, RECOVERING, READY, HALTED };
enum class Side { Buy, Sell };
struct Order {std::string id, symbol; Side side; Quantity quantity; double limit; bool operator==(const Order&) const = default;};
struct Fill {std::string id, order_id; Quantity quantity; double price; bool operator==(const Fill&) const = default;};
struct Snapshot {double cash; std::map<std::string,Quantity> positions; std::vector<Order> open_orders;};
struct Limits {
 double max_order_notional=5000, max_symbol_notional=10000, max_gross_notional=20000;
 double max_drawdown=0.1, max_price_jump=0.2, max_daily_loss=0.05;
 double max_sector_notional=20000;
 std::map<std::string,std::string> sectors{{"XYZ","synthetic"}};
 Quantity max_order_quantity=1000, max_symbol_quantity=2000;
 std::size_t max_open_orders=100;
 Time quote_age_ns=1'000'000'000;
 Time order_timeout_ns=30'000'000'000;
};
class Engine {
 struct Quote {double price; Time timestamp;};
 struct Working {Order original; Quantity remaining; Time submitted_at; Quantity cancelled_remaining=0; bool cancel_requested=false; bool cancelled=false;};
 Limits limits_; State state_=State::BOOT; bool initialized_=false, reconciled_=false;
 Time now_=0, day_=0; double cash_=0, peak_=0, day_start_=0, last_equity_=0;
 static constexpr Time day_ns=86'400'000'000'000;
 std::map<std::string,Quantity> positions_;
 std::map<std::string,Quote> quotes_;
 std::map<std::string,Working> orders_;
 std::map<std::string,Fill> fills_;
 std::map<std::string,std::string> cancel_acks_;
 std::vector<std::string> audit_;
 bool halt(const std::string& reason) {state_=State::HALTED; reconciled_=false; audit_.push_back("HALTED "+reason); return false;}
 bool clock(Time now) {if(now<now_) return halt("clock regression"); now_=now; return true;}
 bool fresh(const Quote& q) const {return q.timestamp<=now_ && now_-q.timestamp<=limits_.quote_age_ns;}
 bool portfolio() {
  long double equity=cash_, gross=0, reserved=0;
  std::map<std::string,long double> exposure, buying, selling;
  for(const auto& [symbol,quantity]:positions_) {
   if(quantity==0) continue;
   auto q=quotes_.find(symbol); if(q==quotes_.end() || !fresh(q->second)) return halt("missing or stale position mark");
   long double value=static_cast<long double>(quantity)*q->second.price;
   if(value>limits_.max_symbol_notional || quantity>limits_.max_symbol_quantity) return halt("symbol exposure");
   gross+=value; equity+=value; exposure[symbol]=value;
  }
  for(const auto& [id,working]:orders_) {
   static_cast<void>(id); if(working.remaining==0) continue;
   if(now_-working.submitted_at>=limits_.order_timeout_ns) return halt("order timeout");
   const auto& o=working.original; auto mark=quotes_.find(o.symbol);
   if(mark==quotes_.end()||!fresh(mark->second)) return halt("stale working order mark");
   if(o.side==Side::Buy) {
    buying[o.symbol]+=working.remaining;
    const long double value=static_cast<long double>(working.remaining)*std::max(o.limit,mark->second.price);
    reserved+=static_cast<long double>(working.remaining)*o.limit; gross+=value; exposure[o.symbol]+=value;
    if(exposure[o.symbol]>limits_.max_symbol_notional) return halt("pending symbol exposure");
   } else selling[o.symbol]+=working.remaining;
  }
  for(const auto& [symbol,quantity]:buying) if(quantity+position(symbol)>limits_.max_symbol_quantity) return halt("pending quantity limit");
  for(const auto& [symbol,quantity]:selling) if(quantity>position(symbol)) return halt("pending sells exceed holdings");
  std::map<std::string,long double> sector_exposure;
  for(const auto& [symbol,value]:exposure) {
   auto sector=limits_.sectors.find(symbol);
   if(sector==limits_.sectors.end()) return halt("missing sector");
   sector_exposure[sector->second]+=value;
  }
  for(const auto& [sector,value]:sector_exposure) {static_cast<void>(sector); if(value>limits_.max_sector_notional) return halt("sector exposure");}
  if(reserved>cash_) return halt("reserved cash exceeds balance");
  if(gross>limits_.max_gross_notional || !std::isfinite(equity) || equity>std::numeric_limits<double>::max()) return halt("portfolio exposure");
  if(now_/day_ns!=day_) {day_=now_/day_ns; day_start_=last_equity_;}
  last_equity_=static_cast<double>(equity);
  if(day_start_>0 && equity<=day_start_*(1-limits_.max_daily_loss)) return halt("daily loss");
  peak_=std::max(peak_,static_cast<double>(equity));
  if(peak_>0 && equity<=peak_*(1-limits_.max_drawdown)) return halt("drawdown");
  return true;
 }
public:
 explicit Engine(Limits limits):limits_(limits) {
  if(!positive(limits.max_order_notional)||!positive(limits.max_symbol_notional)||!positive(limits.max_gross_notional)||
   !positive(limits.max_sector_notional)||!positive(limits.max_daily_loss)||limits.max_daily_loss>=1||limits.sectors.empty()||
   !positive(limits.max_drawdown)||limits.max_drawdown>=1||!positive(limits.max_price_jump)||limits.max_price_jump>=1||
   limits.max_order_quantity<=0||limits.max_symbol_quantity<=0||limits.max_symbol_quantity>1'000'000'000'000LL||
   limits.max_open_orders==0||limits.quote_age_ns<0||limits.order_timeout_ns<=0) throw std::invalid_argument("invalid risk limits");
 }
 State state() const {return state_;}
 double cash() const {return cash_;}
 Quantity position(const std::string& symbol) const {auto p=positions_.find(symbol); return p==positions_.end()?0:p->second;}
 std::size_t open_orders() const {std::size_t n=0; for(const auto& [id,o]:orders_) {static_cast<void>(id); if(o.remaining>0) ++n;} return n;}
 const std::vector<std::string>& audit() const {return audit_;}
 bool poll(Time now) {return clock(now) && portfolio();}
 void queue_overflow() {halt("event queue overflow");}
 void disconnect() {halt("disconnect");}
 bool begin_recovery() {if(state_!=State::BOOT && state_!=State::HALTED) return false; state_=State::RECOVERING; reconciled_=false; audit_.push_back("RECOVERING"); return true;}
 bool reconcile(const Snapshot& snapshot,Time now) {
  if(state_!=State::RECOVERING || !clock(now)) return false;
  if(!nonnegative(snapshot.cash)) return halt("invalid snapshot cash");
  auto positions=snapshot.positions;
  for(auto it=positions.begin();it!=positions.end();) {
   if(it->first.empty()||it->second<0||it->second>limits_.max_symbol_quantity) return halt("invalid snapshot position");
   if(it->second==0) it=positions.erase(it); else ++it;
  }
  if(!initialized_) {
   if(!positions.empty() || !snapshot.open_orders.empty()) return halt("bootstrap requires flat snapshot");
   cash_=snapshot.cash; peak_=cash_; day_start_=cash_; last_equity_=cash_; day_=now_/day_ns; initialized_=true;
  } else {
   auto local=positions_; for(auto it=local.begin();it!=local.end();) {if(it->second==0) it=local.erase(it); else ++it;}
   if(snapshot.cash!=cash_ || positions!=local || snapshot.open_orders.size()!=open_orders()) return halt("snapshot mismatch");
   std::map<std::string,bool> seen;
   for(const auto& order:snapshot.open_orders) {
    auto found=orders_.find(order.id);
    if(found==orders_.end() || !seen.emplace(order.id,true).second) return halt("snapshot order mismatch");
    auto expected=found->second.original; expected.quantity=found->second.remaining;
    if(expected.quantity<=0 || expected!=order) return halt("snapshot order mismatch");
   }
  }
  reconciled_=true; audit_.push_back("snapshot matched"); return true;
 }
 bool restart() {if(state_!=State::RECOVERING||!reconciled_||!portfolio()) return false; state_=State::READY; audit_.push_back("READY manual restart"); return true;}
 bool quote(const std::string& symbol,double price,Time timestamp,Time now) {
  if(!clock(now)) return false;
  if(symbol.empty()||!positive(price)||timestamp<0||timestamp>now||now-timestamp>limits_.quote_age_ns) return halt("invalid quote");
  auto old=quotes_.find(symbol);
  if(old!=quotes_.end()) {
   if(timestamp<old->second.timestamp || (timestamp==old->second.timestamp && price!=old->second.price)) return halt("conflicting quote");
   if(std::abs(price/old->second.price-1)>limits_.max_price_jump) return halt("price jump");
  }
  quotes_[symbol]={price,timestamp}; return portfolio();
 }
 bool submit(const Order& order,Time now) {
  if(!clock(now)||state_!=State::READY) return false;
  if(!portfolio()) return false;
  auto existing=orders_.find(order.id);
  if(existing!=orders_.end()) {if(existing->second.original!=order) return halt("conflicting order id"); return true;}
  if(order.id.empty()||order.symbol.empty()||order.quantity<=0||order.quantity>limits_.max_order_quantity||!positive(order.limit)||
    (order.side!=Side::Buy&&order.side!=Side::Sell)) return false;
  if(!limits_.sectors.contains(order.symbol)) return false;
  auto q=quotes_.find(order.symbol);
  if(q==quotes_.end()||!fresh(q->second)) return halt("missing or stale quote");
  if(!portfolio()) return false;
  const long double notional=static_cast<long double>(order.quantity)*order.limit;
  if(notional>limits_.max_order_notional||open_orders()>=limits_.max_open_orders) return false;
  long double reserved_cash=0, gross=0, symbol_exposure=0, bought=0, sold=0;
  for(const auto& [symbol,qty]:positions_) if(qty) {auto mark=quotes_.at(symbol).price; gross+=static_cast<long double>(qty)*mark; if(symbol==order.symbol) symbol_exposure=static_cast<long double>(qty)*mark;}
  for(const auto& [id,working]:orders_) {
   static_cast<void>(id); if(working.remaining==0) continue;
   const auto& o=working.original;
   if(o.side==Side::Buy) {
    auto mark=quotes_.find(o.symbol); if(mark==quotes_.end()||!fresh(mark->second)) return halt("stale working order mark");
    auto exposure=static_cast<long double>(working.remaining)*std::max(o.limit,mark->second.price);
    reserved_cash+=static_cast<long double>(working.remaining)*o.limit; gross+=exposure;
    if(o.symbol==order.symbol) {bought+=working.remaining; symbol_exposure+=exposure;}
   } else if(o.symbol==order.symbol) sold+=working.remaining;
  }
  if(order.side==Side::Buy) {
   long double sector_exposure=0;
   const auto& sector=limits_.sectors.at(order.symbol);
   for(const auto& [symbol,qty]:positions_) if(qty && limits_.sectors.at(symbol)==sector) sector_exposure+=static_cast<long double>(qty)*quotes_.at(symbol).price;
   for(const auto& [id,w]:orders_) {static_cast<void>(id); if(w.remaining && w.original.side==Side::Buy && limits_.sectors.at(w.original.symbol)==sector) sector_exposure+=static_cast<long double>(w.remaining)*std::max(w.original.limit,quotes_.at(w.original.symbol).price);}
   const long double exposure=static_cast<long double>(order.quantity)*std::max(order.limit,q->second.price);
   if(sector_exposure+exposure>limits_.max_sector_notional) return false;
   if(reserved_cash+notional>cash_ || position(order.symbol)+bought+order.quantity>limits_.max_symbol_quantity ||
     symbol_exposure+exposure>limits_.max_symbol_notional || gross+exposure>limits_.max_gross_notional) return false;
  } else if(order.quantity+sold>position(order.symbol)) return false;
  orders_.emplace(order.id,Working{order,order.quantity,now}); audit_.push_back("accepted "+order.id); return true;
 }
 bool cancel_request(const std::string& order_id) {
  auto found=orders_.find(order_id);
  if(found==orders_.end()) return halt("unknown cancellation order");
  found->second.cancel_requested=true; audit_.push_back("cancel requested "+order_id); return true;
 }
 bool cancel_ack(const std::string& event_id,const std::string& order_id) {
  auto duplicate=cancel_acks_.find(event_id);
  if(duplicate!=cancel_acks_.end()) return duplicate->second==order_id || halt("conflicting cancel event");
  auto found=orders_.find(order_id);
  if(event_id.empty() || found==orders_.end() || !found->second.cancel_requested) return halt("invalid cancel acknowledgement");
  auto& working=found->second;
  if(!working.cancelled) {working.cancelled_remaining=working.remaining; working.remaining=0; working.cancelled=true;}
  cancel_acks_.emplace(event_id,order_id); audit_.push_back("cancel acknowledged "+order_id);
  if(state_==State::RECOVERING) reconciled_=false;
  return true;
 }
 bool fill(const Fill& fill) {
  auto duplicate=fills_.find(fill.id);
  if(duplicate!=fills_.end()) {if(duplicate->second!=fill) return halt("conflicting fill id"); return true;}
  auto found=orders_.find(fill.order_id);
  if(fill.id.empty()||found==orders_.end()||fill.quantity<=0||!positive(fill.price)) return halt("invalid fill");
  auto& working=found->second; const auto& order=working.original;
  if(fill.quantity>working.remaining+working.cancelled_remaining || (order.side==Side::Buy?fill.price>order.limit:fill.price<order.limit)) return halt("fill violates order");
  long double cost=static_cast<long double>(fill.quantity)*fill.price;
  long double next_cash=cash_+(order.side==Side::Buy?-cost:cost);
  if(next_cash<0 || next_cash>std::numeric_limits<double>::max() || !std::isfinite(next_cash)) return halt("fill cash invalid");
  const auto held=position(order.symbol);
  if(order.side==Side::Sell && fill.quantity>held) return halt("fill creates short");
  if(order.side==Side::Buy && fill.quantity>limits_.max_symbol_quantity-held) return halt("fill quantity limit");
  cash_=static_cast<double>(next_cash); positions_[order.symbol]=held+(order.side==Side::Buy?fill.quantity:-fill.quantity);
  if(working.cancelled) working.cancelled_remaining-=fill.quantity; else working.remaining-=fill.quantity;
  fills_.emplace(fill.id,fill); audit_.push_back("fill "+fill.id+" order "+order.id+" quantity "+std::to_string(fill.quantity));
  // A fill is accounted even during HALTED; reconciliation must include it.
  if(state_==State::RECOVERING) reconciled_=false;
  if(working.cancelled) return halt("late fill after cancel acknowledgement; reconcile required");
  return portfolio();
 }
};
} // namespace offline
