#include "execution.hpp"
#include <iostream>
using namespace offline;
int main() {
 Limits limits; limits.sectors={{"DEMO","synthetic"}};
 Engine engine(limits); engine.begin_recovery();
 if(!engine.reconcile({10000,{},{}},0)||!engine.restart()) return 1;
 struct Intent {Quantity quantity; double limit;};
 SpscQueue<Intent,8> intents; Intent intent{};
 if(!intents.push({20,10})||!intents.pop(intent)||!engine.quote("DEMO",10,0,0)) return 2;
 // Preview the full intent on a copy; accepted children reserve real simulated capacity.
 auto preview=engine;
 if(!preview.submit({"parent","DEMO",Side::Buy,intent.quantity,intent.limit},0)) return 2;
 std::cout<<"OFFLINE intent dequeued and parent risk approved\n";
 TokenBucket rate(2,2,0); auto children=schedule(intent.quantity,4,4,0,1,1);
 for(std::size_t i=0;i<children.size();++i) {
  const Time now=static_cast<Time>(i)*1'000'000'000;
  if(!engine.quote("DEMO",10,now,now)||!rate.take(now)) return 2;
  const auto id="offline-"+std::to_string(i);
  if(!engine.submit({id,"DEMO",Side::Buy,children[i],10},now)) return 3;
  const auto first=children[i]/2;
  if(!engine.fill({id+"-partial",id,first,10})||!engine.fill({id+"-final",id,children[i]-first,10})) return 4;
 }
 engine.disconnect(); engine.begin_recovery();
 if(!engine.reconcile({9800,{{"DEMO",20}},{}},3'000'000'000)||!engine.restart()) return 5;
 for(const auto& event:engine.audit()) std::cout<<event<<'\n';
 std::cout<<"OFFLINE ONLY cash="<<engine.cash()<<" position="<<engine.position("DEMO")<<'\n';
}
