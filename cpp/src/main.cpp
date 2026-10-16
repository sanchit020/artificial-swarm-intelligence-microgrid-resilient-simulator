#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <numeric>
#include <queue>
#include <random>
#include <set>
#include <sstream>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

using namespace std;
static constexpr double PI=3.14159265358979323846;
static constexpr int N=50, H=24;
static const vector<string> subs={"S1","S2","S3","S4","S5","S6","S7","S8"};
static const vector<pair<string,string>> mesh={{"S1","S2"},{"S2","S3"},{"S3","S4"},{"S4","S5"},{"S5","S6"},{"S6","S7"},{"S7","S1"},{"S1","S8"},{"S2","S8"},{"S3","S8"},{"S4","S8"},{"S5","S8"},{"S6","S8"},{"S7","S8"},{"S2","S6"},{"S3","S5"}};
static const vector<string> sources={"Solar","Wind","Battery","Main Generator"};
struct Settings { double demandScale=1,solarScale=1,windScale=1,generatorCapacity=150,batteryCapacity=120,batteryPower=35,initialSoc=60,reserveSoc=18,chargeEff=.94,dischargeEff=.94,generatorCost=115,wearCost=8,unservedPenalty=18000,reservePenalty=350; int population=8,generations=3,seed=2026; };
using Edge=pair<string,string>;
struct Config { Settings s; int seed=2026; array<int,H> actions{}; map<Edge,double> lineOverrides,feederOverrides; map<string,double> subOverrides; map<Edge,double> feeders; };
struct FlowResult { double demand=0,delivered=0,unserved=0,criticalDelivered=0,criticalDemand=0; map<string,double> sourceUsed; map<string,double> cd,cu; map<Edge,double> sourceFlow,meshFlow,feedFlow; };
struct Arc {int to,rev; double cap,original;};
struct MaxFlow { vector<vector<Arc>> g; vector<pair<int,int>> refs; explicit MaxFlow(int n):g(n){} void add(int u,int v,double c){int ui=g[u].size(),vi=g[v].size();g[u].push_back({v,vi,c,c});g[v].push_back({u,ui,0,0});refs.push_back({u,ui});} double run(int s,int t){double total=0;for(;;){vector<pair<int,int>> p(g.size(),{-1,-1});queue<int>q;q.push(s);p[s]={s,-1};while(!q.empty()&&p[t].first<0){int u=q.front();q.pop();for(int i=0;i<(int)g[u].size();++i)if(g[u][i].cap>1e-9&&p[g[u][i].to].first<0){p[g[u][i].to]={u,i};q.push(g[u][i].to);if(g[u][i].to==t)break;}}if(p[t].first<0)break;double f=1e100;for(int v=t;v!=s;){auto [u,i]=p[v];f=min(f,g[u][i].cap);v=u;}for(int v=t;v!=s;){auto [u,i]=p[v];auto &a=g[u][i];a.cap-=f;g[v][a.rev].cap+=f;v=u;}total+=f;}return total;} };
static string C(int i){ostringstream o;o<<'C'<<setw(3)<<setfill('0')<<i;return o.str();}
static bool critical(int i){return i==3||i==10||i==17||i==24||i==31||i==38||i==45;}
static map<string,double> demands(){map<string,double>w;double sum=0;for(int i=1;i<=N;i++){double x=(.82+.22*(.5+.5*sin(i*1.73)))*(critical(i)?1.3:1.0);w[C(i)]=x;sum+=x;}for(auto &x:w)x.second=235*x.second/sum;return w;}
static vector<string> split(const string&s,char d){vector<string>v;stringstream ss(s);string x;while(getline(ss,x,d))v.push_back(x);return v;}
static Config readConfig(const string&path){Config c;ifstream f(path);if(!f)throw runtime_error("Cannot read config");string line;while(getline(f,line)){if(line.empty()||line[0]=='#')continue;auto p=line.find('=');if(p==string::npos)continue;string k=line.substr(0,p),v=line.substr(p+1);auto num=[&](){return stod(v);};auto integer=[&](){return stoi(v);};if(k=="seed")c.seed=c.s.seed=integer();else if(k=="demand_scale")c.s.demandScale=num();else if(k=="solar_scale")c.s.solarScale=num();else if(k=="wind_scale")c.s.windScale=num();else if(k=="generator_capacity")c.s.generatorCapacity=num();else if(k=="battery_capacity")c.s.batteryCapacity=num();else if(k=="battery_power")c.s.batteryPower=num();else if(k=="initial_soc")c.s.initialSoc=num();else if(k=="reserve_soc")c.s.reserveSoc=num();else if(k=="charge_efficiency")c.s.chargeEff=num();else if(k=="discharge_efficiency")c.s.dischargeEff=num();else if(k=="generator_cost")c.s.generatorCost=num();else if(k=="battery_wear_cost")c.s.wearCost=num();else if(k=="unserved_penalty")c.s.unservedPenalty=num();else if(k=="reserve_penalty")c.s.reservePenalty=num();else if(k=="population")c.s.population=integer();else if(k=="generations")c.s.generations=integer();else if(k=="actions"){auto a=split(v,',');if(a.size()!=H)throw runtime_error("actions must contain 24 genes");for(int i=0;i<H;i++)c.actions[i]=stoi(a[i]);}else if(k=="line_override"||k=="feeder_override"){auto a=split(v,',');if(a.size()!=3)throw runtime_error("bad edge override");(k=="line_override"?c.lineOverrides:c.feederOverrides)[{a[0],a[1]}]=stod(a[2]);}else if(k=="sub_override"){auto a=split(v,',');if(a.size()!=2)throw runtime_error("bad substation override");c.subOverrides[a[0]]=stod(a[1]);}else if(k=="feeder"){auto a=split(v,',');if(a.size()!=3)throw runtime_error("bad feeder");c.feeders[{a[0],a[1]}]=5.5;}}
 if(c.feeders.size()!=2*N)throw runtime_error("Config must provide two feeders for every consumer (100 edges)");return c;}
static FlowResult allocate(const Config& cfg, double solar, double wind,
                           double batt, double gen, double scale) {
    const auto base = demands();
    map<string, double> d;
    for (const auto& [consumer, value] : base) d[consumer] = value * scale;

    map<string, double> subcap;
    for (const auto& sub : subs) subcap[sub] = 82.0;
    for (const auto& [sub, value] : cfg.subOverrides) {
        if (!subcap.count(sub) || value < 0.0)
            throw runtime_error("Invalid substation override");
        subcap[sub] = value;
    }

    map<Edge, double> sourceCaps, meshCaps, feederCaps;
    const double solarCap[8] = {48, 42, 24, 18, 22, 18, 24, 30};
    const double windCap[8]  = {22, 35, 43, 28, 30, 36, 24, 32};
    for (int i = 0; i < 8; ++i) {
        const bool solarHere = (i == 0 || i == 1 || i == 6 || i == 7);
        const bool windHere = (i == 1 || i == 2 || i == 4 || i == 5);
        const bool batteryHere = (i == 0 || i == 3 || i == 7);
        const bool generatorHere = (i == 2 || i == 3 || i == 6);
        sourceCaps[{"Solar", subs[i]}] = solarHere ? solarCap[i] : 0.0;
        sourceCaps[{"Wind", subs[i]}] = windHere ? windCap[i] : 0.0;
        sourceCaps[{"Battery", subs[i]}] = batteryHere ? 40.0 : 0.0;
        sourceCaps[{"Main Generator", subs[i]}] = generatorHere ? 55.0 : 0.0;
    }
    for (const auto& [a, b] : mesh) {
        meshCaps[{a, b}] = 48.0;
        meshCaps[{b, a}] = 48.0;
    }
    feederCaps = cfg.feeders;

    auto knownLine = [&](const Edge& edge) {
        return sourceCaps.count(edge) || meshCaps.count(edge);
    };
    for (const auto& [edge, cap] : cfg.lineOverrides) {
        if (cap < 0.0 || !knownLine(edge))
            throw runtime_error("Unknown/negative source or transmission edge override: " + edge.first + " -> " + edge.second);
        if (sourceCaps.count(edge)) sourceCaps[edge] = cap;
        else meshCaps[edge] = cap;
    }
    for (const auto& [edge, cap] : cfg.feederOverrides) {
        if (cap < 0.0 || !feederCaps.count(edge))
            throw runtime_error("Unknown/negative feeder override: " + edge.first + " -> " + edge.second);
        feederCaps[edge] = cap;
    }
    for (const auto& sub : subs) {
        if (subcap[sub] == 0.0) {
            for (auto& [edge, cap] : sourceCaps) if (edge.second == sub) cap = 0.0;
            for (auto& [edge, cap] : meshCaps)
                if (edge.first == sub || edge.second == sub) cap = 0.0;
            for (auto& [edge, cap] : feederCaps) if (edge.first == sub) cap = 0.0;
        }
    }

    map<string, double> supply = {
        {"Solar", max(0.0, solar)}, {"Wind", max(0.0, wind)},
        {"Battery", max(0.0, batt)}, {"Main Generator", max(0.0, gen)}
    };

    FlowResult out;
    out.demand = accumulate(d.begin(), d.end(), 0.0,
        [](double total, const auto& item) { return total + item.second; });
    for (const auto& [consumer, value] : d) {
        out.cd[consumer] = 0.0;
        out.cu[consumer] = value;
    }
    for (const auto& source : sources) out.sourceUsed[source] = 0.0;
    for (const auto& [edge, cap] : sourceCaps) out.sourceFlow[edge] = 0.0;
    for (const auto& [edge, cap] : meshCaps) out.meshFlow[edge] = 0.0;
    for (const auto& [edge, cap] : feederCaps) out.feedFlow[edge] = 0.0;

    // Construct one residual network for both priority stages. Running the
    // second augmentation on the SAME residual graph is essential: it allows
    // Edmonds-Karp to reroute earlier critical-consumer paths to free capacity
    // for noncritical demand without reducing already-served critical demand.
    vector<string> nodes = {"SRC", "SINK"};
    auto addNode = [&](const string& node) {
        if (find(nodes.begin(), nodes.end(), node) == nodes.end()) nodes.push_back(node);
    };
    for (const auto& [source, value] : supply) addNode("SUP:" + source);
    for (const auto& [edge, cap] : sourceCaps) {
        addNode("SRC:" + edge.first); addNode(edge.second + ":in");
    }
    for (const auto& sub : subs) { addNode(sub + ":in"); addNode(sub + ":out"); }
    for (const auto& [edge, cap] : meshCaps) {
        addNode(edge.first + ":out"); addNode(edge.second + ":in");
    }
    for (const auto& [edge, cap] : feederCaps) {
        addNode(edge.first + ":out"); addNode(edge.second);
    }
    for (int i = 1; i <= N; ++i) addNode(C(i));
    auto id = [&](const string& node) {
        auto it = find(nodes.begin(), nodes.end(), node);
        if (it == nodes.end()) throw runtime_error("Internal network node missing: " + node);
        return int(it - nodes.begin());
    };

    struct ArcKey { string type, a, b; };
    vector<ArcKey> keys;
    MaxFlow mf(static_cast<int>(nodes.size()));
    auto addArc = [&](const string& u, const string& v, double cap, ArcKey key) {
        mf.add(id(u), id(v), max(0.0, cap));
        keys.push_back(move(key));
    };
    for (const auto& [source, cap] : supply)
        addArc("SRC", "SUP:" + source, cap, {"supply", source, ""});
    for (const auto& [edge, cap] : sourceCaps)
        addArc("SUP:" + edge.first, edge.second + ":in", cap, {"source", edge.first, edge.second});
    for (const auto& sub : subs)
        addArc(sub + ":in", sub + ":out", subcap[sub], {"sub", sub, ""});
    for (const auto& [edge, cap] : meshCaps)
        addArc(edge.first + ":out", edge.second + ":in", cap, {"mesh", edge.first, edge.second});
    for (const auto& [edge, cap] : feederCaps)
        addArc(edge.first + ":out", edge.second, cap, {"feed", edge.first, edge.second});

    // First maximize critical service.
    for (int i = 1; i <= N; ++i) {
        const string consumer = C(i);
        if (critical(i))
            addArc(consumer, "SINK", d[consumer], {"consumer", consumer, ""});
    }
    mf.run(id("SRC"), id("SINK"));

    // Then maximize total service while retaining critical priority, continuing
    // on the same residual graph so earlier routes can be rearranged safely.
    for (int i = 1; i <= N; ++i) {
        const string consumer = C(i);
        if (!critical(i))
            addArc(consumer, "SINK", d[consumer], {"consumer", consumer, ""});
    }
    mf.run(id("SRC"), id("SINK"));

    for (size_t ix = 0; ix < keys.size(); ++ix) {
        const auto [u, j] = mf.refs[ix];
        const auto& arc = mf.g[u][j];
        const double used = max(0.0, arc.original - arc.cap);
        const auto& key = keys[ix];
        if (key.type == "supply") out.sourceUsed[key.a] += used;
        else if (key.type == "source") out.sourceFlow[{key.a, key.b}] += used;
        else if (key.type == "mesh") out.meshFlow[{key.a, key.b}] += used;
        else if (key.type == "feed") out.feedFlow[{key.a, key.b}] += used;
        else if (key.type == "consumer") {
            out.cd[key.a] += used;
            out.cu[key.a] = max(0.0, d[key.a] - out.cd[key.a]);
        }
    }
    out.delivered = accumulate(out.cd.begin(), out.cd.end(), 0.0,
        [](double total, const auto& item) { return total + item.second; });
    out.unserved = max(0.0, out.demand - out.delivered);
    for (int i = 1; i <= N; ++i) if (critical(i)) {
        out.criticalDemand += d[C(i)];
        out.criticalDelivered += out.cd[C(i)];
    }
    return out;
}

struct Sim { vector<map<string,double>> rows; double cost=0,unserved=0,delivered=0,demand=0,generator=0,curtailment=0,throughput=0,finalSoc=0,objective=0,criticalDelivered=0,criticalDemand=0;double criticalPct=100;};
static Sim simulate(const Config&cfg,const array<int,H>&actions){const auto&s=cfg.s;if(s.batteryCapacity<=0||s.batteryPower<0||s.chargeEff<=0||s.chargeEff>1||s.dischargeEff<=0||s.dischargeEff>1)throw runtime_error("Invalid battery settings");mt19937_64 rng(cfg.seed);normal_distribution<double> nd(0,1);double demand[H],solar[H],wind[H];for(int h=0;h<H;h++){double base=150+25*sin((h-7)*2*PI/24)+18*exp(-pow((h-19)/3.2,2));double ss=max(0.0,sin((h-6)*PI/12));double ww=clamp(.52+.18*sin((h+2)*2*PI/24)+.08*cos(h*4*PI/24),.18,.9)/.9;demand[h]=max(120.0,base*s.demandScale*(1+nd(rng)*.025));solar[h]=max(0.0,145*ss*s.solarScale*(1+nd(rng)*.04));wind[h]=max(0.0,55*ww*s.windScale*(1+nd(rng)*.05));}
 // Use one deterministic stream per profile and preserve identical profiles for all candidates.
 // Profile generation uses seed-local randomness; optimizer evaluates identical scenarios.
 double reserve=clamp(s.reserveSoc,0.0,s.batteryCapacity),soc=clamp(s.initialSoc,0.0,s.batteryCapacity);Sim out;auto base=demands();
 for(int h=0;h<H;h++){int a=actions[h];if(a < -2||a>2)throw runtime_error("Battery actions must be -2..2");double charge=0,discharge=0,ren=solar[h]+wind[h];if(a>0){double wanted=s.batteryPower*a/2.0,room=max(0.0,s.batteryCapacity-soc)/s.chargeEff;charge=min({wanted,room,max(0.0,ren-demand[h])});soc=min(s.batteryCapacity,soc+charge*s.chargeEff);}else if(a<0){double wanted=s.batteryPower*abs(a)/2.0,avail=max(0.0,soc-reserve)*s.dischargeEff;discharge=min(wanted,avail);soc=max(0.0,soc-discharge/s.dischargeEff);}double solarCharge=min(charge,solar[h]),windCharge=max(0.0,charge-solarCharge),solarGrid=max(0.0,solar[h]-solarCharge),windGrid=max(0.0,wind[h]-windCharge);auto f=allocate(cfg,solarGrid,windGrid,discharge,max(0.0,s.generatorCapacity),demand[h]/235.0);double actualBatt=f.sourceUsed["Battery"];if(discharge>0&&actualBatt<discharge)soc=min(s.batteryCapacity,soc+(discharge-actualBatt)/s.dischargeEff);discharge=actualBatt;double gc=f.sourceUsed["Main Generator"],curt=max(0.0,solarGrid-f.sourceUsed["Solar"])+max(0.0,windGrid-f.sourceUsed["Wind"]),wear=(charge+discharge)*s.wearCost,cost=gc*s.generatorCost+wear+f.unserved*s.unservedPenalty;out.cost+=cost;out.unserved+=f.unserved;out.delivered+=f.delivered;out.demand+=f.demand;out.generator+=gc;out.curtailment+=curt;out.throughput+=charge+discharge;out.criticalDelivered+=f.criticalDelivered;out.criticalDemand+=f.criticalDemand;map<string,double> r;r["Hour"]=h;r["Demand (MW)"]=f.demand;r["Solar (MW)"]=solar[h];r["Wind (MW)"]=wind[h];r["Battery charge (MW)"]=charge;r["Battery discharge (MW)"]=discharge;r["Generator used (MW)"]=gc;r["Delivered (MW)"]=f.delivered;r["Unserved (MW)"]=f.unserved;r["Source flow balance residual (MW)"]=accumulate(f.sourceUsed.begin(),f.sourceUsed.end(),0.0,[](double z,const auto&x){return z+x.second;})-f.delivered;r["Consumer delivery balance residual (MW)"]=f.delivered-f.delivered;r["Battery SOC (MWh)"]=soc;r["Operating cost"]=cost;r["Reserve shortfall (MWh)"]=max(0.0,reserve-soc);for(int di=1;di<=8;di++){r["D"+to_string(di)+" demand (MW)"]=0;r["D"+to_string(di)+" delivered (MW)"]=0;}for(int ci=1;ci<=N;ci++){string c=C(ci);int di=min(8,((ci-1)*8)/50+1);r[c+" delivered (MW)"]=f.cd[c];r[c+" demand (MW)"]=base[c]*demand[h]/235.0;r[c+" unserved (MW)"]=max(0.0,r[c+" demand (MW)"]-f.cd[c]);r["D"+to_string(di)+" demand (MW)"]+=r[c+" demand (MW)"];r["D"+to_string(di)+" delivered (MW)"]+=f.cd[c];}for(auto [e,v]:f.feedFlow)r["Feeder "+e.first+" -> "+e.second+" flow (MW)"]=v;for(auto [e,v]:f.sourceFlow)r["Source line "+e.first+" -> "+e.second+" flow (MW)"]=v;for(auto [e,v]:f.meshFlow)r["Transmission "+e.first+" -> "+e.second+" flow (MW)"]=v;out.rows.push_back(move(r));}
 out.finalSoc=soc;out.objective=out.cost+max(0.0,reserve-soc)*s.reservePenalty;out.criticalPct=100*out.criticalDelivered/max(1e-9,out.criticalDemand);return out;}
static pair<array<int,H>,Sim> optimize(Config cfg){mt19937 rng(cfg.seed);int pop=max(8,cfg.s.population),gens=max(1,cfg.s.generations);vector<array<int,H>> p(pop);uniform_int_distribution<int>gene(-2,2);for(auto &a:p)for(auto &x:a)x=gene(rng);p.back().fill(0);map<array<int,H>,Sim>cache;auto score=[&](const array<int,H>&a)->double{auto it=cache.find(a);if(it==cache.end())it=cache.emplace(a,simulate(cfg,a)).first;return it->second.objective;};for(int g=0;g<gens;g++){sort(p.begin(),p.end(),[&](auto&a,auto&b){return score(a)<score(b);});vector<array<int,H>>q{p[0],p[1]};while((int)q.size()<pop){uniform_int_distribution<int>pick(0,pop-1),cutd(1,23);auto a=p[pick(rng)],b=p[pick(rng)];int cut=cutd(rng);array<int,H>c=a;for(int i=cut;i<H;i++)c[i]=b[i];uniform_real_distribution<double>prob(0,1);for(auto &x:c)if(prob(rng)<.1)x=gene(rng);q.push_back(c);}p=move(q);}array<int,H> noAction{};auto best=*min_element(p.begin(),p.end(),[&](auto&a,auto&b){return score(a)<score(b);});if(score(noAction)<score(best))best=noAction;return {best,simulate(cfg,best)};}
static string csvq(string s){if(s.find_first_of(",\"\n")!=string::npos){string o="\"";for(char c:s){if(c=='\"')o+="\"\"";else o+=c;}return o+"\"";}return s;}
int main(int argc,char**argv){try{if(argc!=4){cerr<<"usage: asi_engine config.txt hourly.csv summary.txt\n";return 2;}Config c=readConfig(argv[1]);string mode="simulate";{ifstream f(argv[1]);string l;while(getline(f,l))if(l.rfind("mode=",0)==0)mode=l.substr(5);}array<int,H>a=c.actions;Sim result;if(mode=="optimize"){auto z=optimize(c);a=z.first;result=z.second;}else result=simulate(c,a);ofstream csv(argv[2]);if(!csv)throw runtime_error("Cannot write hourly CSV");csv<<setprecision(12);set<string> cols;for(auto&r:result.rows)for(auto&x:r)cols.insert(x.first);csv<<"Hour";for(auto&k:cols)if(k!="Hour")csv<<","<<csvq(k);csv<<"\n";for(auto&r:result.rows){csv<<r.at("Hour");for(auto&k:cols)if(k!="Hour")csv<<","<<(r.count(k)?r.at(k):0.0);csv<<"\n";}ofstream sum(argv[3]);sum<<setprecision(15)<<"actions=";for(int i=0;i<H;i++)sum<<(i?",":"")<<a[i];sum<<"\ncost="<<result.cost<<"\nunserved="<<result.unserved<<"\ndelivered="<<result.delivered<<"\ndemand="<<result.demand<<"\ngenerator="<<result.generator<<"\ncurtailment="<<result.curtailment<<"\nthroughput="<<result.throughput<<"\nfinal_soc="<<result.finalSoc<<"\nobjective="<<result.objective<<"\ncritical_delivered="<<result.criticalDelivered<<"\ncritical_demand="<<result.criticalDemand<<"\ncritical_service_pct="<<result.criticalPct<<"\n";return 0;}catch(const exception&e){cerr<<"ASI C++ engine error: "<<e.what()<<"\n";return 1;}}
