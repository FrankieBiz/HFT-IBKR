#include "execution.hpp"
#include <cassert>
#include <iostream>
#include <numeric>
#include <thread>
using namespace offline;
template<class F> void invalid(F f) { bool caught=false; try {f();} catch(const std::invalid_argument&) {caught=true;} assert(caught); }
int main() {
 SpscQueue<int,2> small; int value=0; assert(!small.pop(value)); assert(small.push(1)); assert(small.push(2)); assert(!small.push(3)); assert(small.overflows()==1); assert(small.pop(value)&&value==1); assert(small.pop(value)&&value==2);
 SpscQueue<int,64> queue; std::thread producer([&]{for(int i=0;i<100000;++i) while(!queue.push(i)) std::this_thread::yield();});
 for(int i=0;i<100000;++i) {while(!queue.pop(value)) std::this_thread::yield(); assert(value==i);} producer.join();
 auto twap=schedule(101,10,10,0,1,1); assert(std::accumulate(twap.begin(),twap.end(),Quantity{0})==101); assert(twap.front()>=10&&twap.back()<=11);
 auto fast=schedule(101,10,10,1e200,1e100,1e-100); assert(std::accumulate(fast.begin(),fast.end(),Quantity{0})==101); assert(fast.front()==101);
 invalid([]{schedule(0,10,1,0,1,1);}); invalid([]{schedule(1,0,1,0,1,1);}); invalid([]{schedule(1,1,1,-1,1,1);}); invalid([]{schedule(1,1,1,0,1,0);});
 TokenBucket bucket(2,1,0); assert(bucket.take(0)); assert(bucket.take(0)); assert(!bucket.take(0)); assert(bucket.take(1'000'000'000)); assert(!bucket.take(0)); invalid([]{TokenBucket b(0,1,0);});
 Limits limits; Engine engine(limits); assert(engine.state()==State::BOOT); assert(!engine.submit({"a","XYZ",Side::Buy,10,10},0)); assert(engine.begin_recovery()); assert(engine.reconcile({10000,{},{}},0)); assert(engine.state()==State::RECOVERING); assert(engine.restart()); assert(engine.quote("XYZ",10,0,0));
 Order order{"a","XYZ",Side::Buy,10,10}; assert(engine.submit(order,0)); assert(engine.submit(order,0)); assert(engine.open_orders()==1); assert(engine.fill({"f1","a",4,10})); assert(engine.fill({"f1","a",4,10})); assert(engine.position("XYZ")==4); assert(engine.fill({"f2","a",6,10})); assert(engine.position("XYZ")==10); assert(engine.cash()==9900); assert(engine.open_orders()==0);
 assert(!engine.submit({"sell","XYZ",Side::Sell,11,10},0)); engine.disconnect(); assert(engine.state()==State::HALTED); assert(!engine.restart()); assert(engine.begin_recovery()); assert(!engine.reconcile({9900,{{"XYZ",9}},{}},0)); assert(engine.state()==State::HALTED);
 Engine recovered(limits); assert(recovered.begin_recovery()); assert(recovered.reconcile({10000,{},{}},0)); assert(recovered.restart()); assert(!recovered.quote("XYZ",10,1,0)); assert(recovered.state()==State::HALTED);
 Engine conflict(limits); conflict.begin_recovery(); conflict.reconcile({10000,{},{}},0); conflict.restart(); conflict.quote("XYZ",10,0,0); assert(conflict.submit(order,0)); assert(!conflict.submit({"a","XYZ",Side::Buy,11,10},0)); assert(conflict.state()==State::HALTED);
 Engine jump(limits); jump.begin_recovery(); jump.reconcile({10000,{},{}},0); jump.restart(); assert(jump.quote("XYZ",10,0,0)); assert(!jump.quote("XYZ",20,1,1));
 Engine stale(limits); stale.begin_recovery(); stale.reconcile({10000,{},{}},0); stale.restart(); stale.quote("XYZ",10,0,0); assert(!stale.submit(order,limits.quote_age_ns+1));
 auto ready=[](Limits l=Limits{},double cash=10000) {Engine e(l); assert(e.begin_recovery()); assert(e.reconcile({cash,{},{}},0)); assert(e.restart()); assert(e.quote("XYZ",10,0,0)); return e;};
 auto cashlimited=ready(limits,50); assert(!cashlimited.submit(order,0));
 auto orderlimit=ready(); assert(!orderlimit.submit({"large","XYZ",Side::Buy,1001,10},0));
 auto nan=std::numeric_limits<double>::quiet_NaN(); auto badprice=ready(); assert(!badprice.submit({"bad","XYZ",Side::Buy,1,nan},0)); assert(!badprice.quote("XYZ",nan,1,1));
 invalid([&]{schedule(1,1,nan,0,1,1);}); invalid([&]{TokenBucket b(1,nan,0);});
 auto duplicatefill=ready(); assert(duplicatefill.submit(order,0)); assert(duplicatefill.fill({"f","a",4,10})); assert(!duplicatefill.fill({"f","a",5,10})); assert(duplicatefill.position("XYZ")==4);
 auto overfill=ready(); assert(overfill.submit(order,0)); assert(!overfill.fill({"f","a",11,10})); assert(overfill.position("XYZ")==0);
 auto partial=ready(); assert(partial.submit(order,0)); assert(partial.fill({"f","a",4,10})); partial.disconnect(); assert(partial.begin_recovery()); assert(partial.reconcile({9960,{{"XYZ",4}},{{"a","XYZ",Side::Buy,6,10}}},0)); assert(partial.restart()); assert(partial.fill({"g","a",6,10}));
 auto haltedfill=ready(); assert(haltedfill.submit(order,0)); haltedfill.disconnect(); assert(haltedfill.fill({"late","a",4,10})); assert(haltedfill.state()==State::HALTED); assert(haltedfill.position("XYZ")==4);
 auto ddlimits=limits; ddlimits.max_drawdown=0.001; auto drawdown=ready(ddlimits); assert(drawdown.submit(order,0)); assert(drawdown.fill({"f","a",10,10})); assert(!drawdown.quote("XYZ",8.5,1,1));
 auto exposurelimits=limits; exposurelimits.max_symbol_notional=100; auto exposure=ready(exposurelimits); assert(exposure.submit(order,0)); assert(!exposure.submit({"more","XYZ",Side::Buy,1,10},0)); assert(!exposure.quote("XYZ",11,1,1));
 auto sells=ready(); assert(sells.submit(order,0)); assert(sells.fill({"f","a",10,10})); assert(sells.submit({"s1","XYZ",Side::Sell,7,10},0)); assert(!sells.submit({"s2","XYZ",Side::Sell,4,10},0)); assert(sells.fill({"sale","s1",7,10})); assert(sells.position("XYZ")==3);
 auto regressed=ready(); assert(regressed.quote("XYZ",10,1,1)); assert(!regressed.submit(order,0));
 auto ac=schedule(100000,10,10,1,1,1); assert(ac.front()>ac.back()); for(auto x:ac) assert(x>=0); assert(std::accumulate(ac.begin(),ac.end(),Quantity{0})==100000);
 auto timeoutlimits=limits; timeoutlimits.order_timeout_ns=100; auto timeout=ready(timeoutlimits); assert(timeout.submit(order,0)); assert(timeout.poll(99)); assert(!timeout.poll(100)); assert(timeout.state()==State::HALTED);
 auto dup_timeout=ready(timeoutlimits); assert(dup_timeout.submit(order,0)); assert(!dup_timeout.submit(order,100)); assert(dup_timeout.state()==State::HALTED);
 invalid([]{TokenBucket huge(1e20,1,0);});
 auto boundarylimits=limits; boundarylimits.max_drawdown=.001; auto boundary=ready(boundarylimits); boundary.submit(order,0); boundary.fill({"b","a",10,10}); assert(!boundary.quote("XYZ",9,1,1));
 auto overflowed=ready(); SpscQueue<int,1> eventqueue; assert(eventqueue.push(1)); if(!eventqueue.push(2)) overflowed.queue_overflow(); assert(overflowed.state()==State::HALTED);
 auto cancelled=ready(); assert(cancelled.submit(order,0)); assert(cancelled.fill({"first","a",4,10})); assert(cancelled.cancel_request("a")); assert(cancelled.cancel_ack("ack1","a")); assert(cancelled.cancel_ack("ack1","a")); assert(cancelled.open_orders()==0); cancelled.disconnect(); assert(cancelled.begin_recovery()); assert(cancelled.reconcile({9960,{{"XYZ",4}},{}},0)); assert(cancelled.restart()); assert(!cancelled.fill({"latecancel","a",2,10})); assert(cancelled.position("XYZ")==6); assert(cancelled.state()==State::HALTED);
 auto sectorlimits=limits; sectorlimits.max_sector_notional=50; auto sector=ready(sectorlimits); assert(!sector.submit(order,0));
 auto dailylimits=limits; dailylimits.max_daily_loss=.001; auto daily=ready(dailylimits); daily.submit(order,0); daily.fill({"d","a",10,10}); assert(!daily.quote("XYZ",9,1,1));
 auto qlimits=limits; qlimits.max_symbol_quantity=10; auto replacement=ready(qlimits); assert(replacement.submit(order,0)); replacement.cancel_request("a"); replacement.cancel_ack("ca","a"); assert(replacement.submit({"replacement","XYZ",Side::Buy,10,10},0)); assert(!replacement.fill({"late","a",1,10})); assert(replacement.begin_recovery()); assert(replacement.reconcile({9990,{{"XYZ",1}},{{"replacement","XYZ",Side::Buy,10,10}}},0)); assert(!replacement.restart());
 auto sellreplacement=ready(); sellreplacement.submit(order,0); sellreplacement.fill({"b","a",10,10}); sellreplacement.submit({"sell-old","XYZ",Side::Sell,10,10},0); sellreplacement.cancel_request("sell-old"); sellreplacement.cancel_ack("cs","sell-old"); assert(sellreplacement.submit({"sell-new","XYZ",Side::Sell,10,10},0)); assert(!sellreplacement.fill({"late-sale","sell-old",1,10})); assert(sellreplacement.begin_recovery()); assert(sellreplacement.reconcile({9910,{{"XYZ",9}},{{"sell-new","XYZ",Side::Sell,10,10}}},0)); assert(!sellreplacement.restart());
 std::cout<<"native tests passed\n";
}
