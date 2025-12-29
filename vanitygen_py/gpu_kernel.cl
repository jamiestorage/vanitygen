/*
 * OpenCL kernel for GPU-accelerated vanity address generation with balance checking
 * True GPU acceleration with real SECP256K1 EC operations.
 */

typedef uint bn_word;
typedef struct { bn_word d[8]; } bignum;

#define MODULUS_BYTES 0xfffffc2f, 0xfffffffe, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff, 0xffffffff
__constant bn_word modulus[] = { MODULUS_BYTES };
__constant bn_word mont_n0 = 0xd2253531;
__constant bn_word mont_rr[] = { 0xe90a1, 0x7a2, 0x1, 0, 0, 0, 0, 0 };

__constant char BASE58_CHARS[] = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";

#define bswap32(v) (((v) >> 24) | (((v) >> 8) & 0xff00) | (((v) << 8) & 0xff0000) | ((v) << 24))

// BIGNUM Basic Ops
void bn_rshift1(bignum *bn) {
    for (int i = 0; i < 7; i++) bn->d[i] = (bn->d[i+1] << 31) | (bn->d[i] >> 1);
    bn->d[7] >>= 1;
}

bn_word bn_uadd_c(bignum *r, bignum *a, __constant bn_word *b) {
    ulong t, c = 0;
    for (int i = 0; i < 8; i++) { t = (ulong)a->d[i] + b[i] + c; r->d[i] = (bn_word)t; c = t >> 32; }
    return (bn_word)c;
}

bn_word bn_uadd(bignum *r, bignum *a, bignum *b) {
    ulong t, c = 0;
    for (int i = 0; i < 8; i++) { t = (ulong)a->d[i] + b->d[i] + c; r->d[i] = (bn_word)t; c = t >> 32; }
    return (bn_word)c;
}

bn_word bn_usub(bignum *r, bignum *a, bignum *b) {
    long t, c = 0;
    for (int i = 0; i < 8; i++) { t = (long)a->d[i] - (long)b->d[i] - c; r->d[i] = (bn_word)t; c = (t < 0) ? 1 : 0; }
    return (bn_word)c;
}

bn_word bn_usub_c(bignum *r, bignum *a, __constant bn_word *b) {
    long t, c = 0;
    for (int i = 0; i < 8; i++) { t = (long)a->d[i] - (long)b[i] - c; r->d[i] = (bn_word)t; c = (t < 0) ? 1 : 0; }
    return (bn_word)c;
}

int bn_ucmp_ge(bignum *a, bignum *b) {
    for (int i = 7; i >= 0; i--) { if (a->d[i] > b->d[i]) return 1; if (a->d[i] < b->d[i]) return 0; }
    return 1;
}

int bn_ucmp_ge_c(bignum *a, __constant bn_word *b) {
    for (int i = 7; i >= 0; i--) { if (a->d[i] > b[i]) return 1; if (a->d[i] < b[i]) return 0; }
    return 1;
}

void bn_mod_add(bignum *r, bignum *a, bignum *b) { if (bn_uadd(r, a, b) || bn_ucmp_ge_c(r, modulus)) bn_usub_c(r, r, modulus); }
void bn_mod_sub(bignum *r, bignum *a, bignum *b) { if (bn_usub(r, a, b)) bn_uadd_c(r, r, modulus); }

// Montgomery multiplication
#define bn_mul_add_word(r, a, w, c) do { \
    ulong _tmp = (ulong)(a) * (w) + (r) + (c); \
    (r) = (uint)_tmp; \
    (c) = _tmp >> 32; \
} while (0)

void bn_mul_mont(bignum *r, bignum *a, bignum *b) {
    uint t[9] = {0};
    uint tea = 0;
    for (int i = 0; i < 8; i++) {
        ulong c = 0;
        for (int j = 0; j < 8; j++) bn_mul_add_word(t[j], a->d[j], b->d[i], c);
        uint m_carry = (uint)c;
        uint m = t[0] * mont_n0;
        c = 0;
        bn_mul_add_word(t[0], modulus[0], m, c);
        for (int j = 1; j < 8; j++) {
            bn_mul_add_word(t[j], modulus[j], m, c);
            t[j-1] = t[j];
        }
        t[7] = m_carry + (uint)c + tea;
        tea = (t[7] < tea || (t[7] == tea && c > 0)) ? 1 : 0; // Very simplified carry handling
    }
    // Final reduction
    bignum res; for(int i=0; i<8; i++) res.d[i] = t[i];
    if (tea || bn_ucmp_ge_c(&res, modulus)) bn_usub_c(&res, &res, modulus);
    *r = res;
}

void bn_mod_inverse(bignum *r, bignum *n) {
    bignum a, b, x, y; for (int i = 0; i < 8; i++) { a.d[i] = modulus[i]; x.d[i] = 0; y.d[i] = 0; }
    b = *n; x.d[0] = 1; bn_word xc = 0, yc = 0;
    while (!(b.d[0]==0 && b.d[1]==0 && b.d[2]==0 && b.d[3]==0 && b.d[4]==0 && b.d[5]==0 && b.d[6]==0 && b.d[7]==0)) {
        while (!(b.d[0] & 1)) {
            if (x.d[0] & 1) xc += bn_uadd_c(&x, &x, modulus);
            bn_rshift1(&x); x.d[7] |= (xc << 31); xc >>= 1;
            bn_rshift1(&b);
        }
        while (!(a.d[0] & 1)) {
            if (y.d[0] & 1) yc += bn_uadd_c(&y, &y, modulus);
            bn_rshift1(&y); y.d[7] |= (yc << 31); yc >>= 1;
            bn_rshift1(&a);
        }
        if (bn_ucmp_ge(&b, &a)) { bn_mod_sub(&b, &b, &a); bn_mod_sub(&x, &x, &y); }
        else { bn_mod_sub(&a, &a, &b); bn_mod_sub(&y, &y, &x); }
    }
    while (yc < 0x80000000) yc -= bn_usub_c(&y, &y, modulus);
    for(int i=0; i<8; i++) y.d[i] = ~y.d[i];
    bn_word carry = 1; for(int i=0; i<8; i++) { ulong t = (ulong)y.d[i] + (ulong)carry; y.d[i] = (bn_word)t; carry = (bn_word)(t >> 32); }
    *r = y;
}

void bn_to_mont(bignum *r, bignum *a) { bignum rr; for(int i=0; i<8; i++) rr.d[i] = mont_rr[i]; bn_mul_mont(r, a, &rr); }
void bn_from_mont(bignum *r, bignum *a) { bignum one; for(int i=0; i<8; i++) one.d[i] = 0; one.d[0] = 1; bn_mul_mont(r, a, &one); }

// SECP256K1 Point Ops
__constant bn_word Gx[] = { 0x16F81798, 0x59F2815B, 0x2DCE28D9, 0x029BFCDB, 0xCE870B07, 0x55A06295, 0xF9DCBBAC, 0x79BE667E };
__constant bn_word Gy[] = { 0x483ADA77, 0x26A3C465, 0x5DA4FBFC, 0x0E1108A8, 0xFD17B448, 0xA6855419, 0x9C47D08F, 0xFB10D4B8 };

typedef struct { bignum x, y, z; } point_j;

void point_j_double(point_j *p) {
    if (p->z.d[0]==0 && p->z.d[1]==0 && p->z.d[2]==0 && p->z.d[3]==0 && p->z.d[4]==0 && p->z.d[5]==0 && p->z.d[6]==0 && p->z.d[7]==0) return;
    bignum s, m, t1, t2, x, y, z;
    bn_mul_mont(&t1, &p->y, &p->y); bn_mul_mont(&s, &p->x, &t1); bn_mod_add(&s, &s, &s); bn_mod_add(&s, &s, &s);
    bn_mul_mont(&t2, &p->x, &p->x); bn_mod_add(&m, &t2, &t2); bn_mod_add(&m, &m, &t2);
    bn_mul_mont(&x, &m, &m); bn_mod_sub(&x, &x, &s); bn_mod_sub(&x, &x, &s);
    bn_mul_mont(&z, &p->y, &p->z); bn_mod_add(&p->z, &z, &z);
    bn_mod_sub(&t2, &s, &x); bn_mul_mont(&y, &m, &t2);
    bn_mul_mont(&t1, &t1, &t1); bn_mod_add(&t1, &t1, &t1); bn_mod_add(&t1, &t1, &t1); bn_mod_add(&t1, &t1, &t1);
    bn_mod_sub(&p->y, &y, &t1); p->x = x;
}

void point_j_add(point_j *p, point_j *q) {
    if (q->z.d[0]==0 && q->z.d[1]==0 && q->z.d[2]==0 && q->z.d[3]==0 && q->z.d[4]==0 && q->z.d[5]==0 && q->z.d[6]==0 && q->z.d[7]==0) return;
    if (p->z.d[0]==0 && p->z.d[1]==0 && p->z.d[2]==0 && p->z.d[3]==0 && p->z.d[4]==0 && p->z.d[5]==0 && p->z.d[6]==0 && p->z.d[7]==0) { *p = *q; return; }
    bignum z1z1, z2z2, u1, u2, s1, s2, h, r, t1, t2;
    bn_mul_mont(&z1z1, &p->z, &p->z); bn_mul_mont(&z2z2, &q->z, &q->z);
    bn_mul_mont(&u1, &p->x, &z2z2); bn_mul_mont(&u2, &q->x, &z1z1);
    bn_mul_mont(&t1, &p->z, &z1z1); bn_mul_mont(&s1, &p->y, &t1);
    bn_mul_mont(&t2, &q->z, &z2z2); bn_mul_mont(&s2, &q->y, &t2);
    if (bn_ucmp_ge(&u1, &u2) && bn_ucmp_ge(&u2, &u1)) { if (bn_ucmp_ge(&s1, &s2) && bn_ucmp_ge(&s2, &s1)) point_j_double(p); else { for(int i=0; i<8; i++) p->z.d[i]=0; } return; }
    bn_mod_sub(&h, &u2, &u1); bn_mod_sub(&r, &s2, &s1);
    bn_mul_mont(&t1, &p->z, &q->z); bn_mul_mont(&p->z, &t1, &h);
    bn_mul_mont(&t1, &h, &h); bn_mul_mont(&t2, &t1, &h); bn_mul_mont(&u1, &u1, &t1);
    bn_mul_mont(&p->x, &r, &r); bn_mod_sub(&p->x, &p->x, &t2); bn_mod_sub(&p->x, &p->x, &u1); bn_mod_sub(&p->x, &p->x, &u1);
    bn_mod_sub(&t1, &u1, &p->x); bn_mul_mont(&p->y, &r, &t1); bn_mul_mont(&t1, &s1, &t2); bn_mod_sub(&p->y, &p->y, &t1);
}

void scalar_mult_g(point_j *res, bignum *k) {
    point_j base, curr; for(int i=0; i<8; i++){ base.x.d[i]=Gx[i]; base.y.d[i]=Gy[i]; base.z.d[i]=0; curr.z.d[i]=0; }
    base.z.d[0]=1; bignum rr; for(int i=0; i<8; i++) rr.d[i]=mont_rr[i];
    bn_to_mont(&base.x, &base.x); bn_to_mont(&base.y, &base.y); bn_to_mont(&base.z, &base.z);
    for (int i = 255; i >= 0; i--) {
        point_j_double(&curr);
        if ((k->d[i / 32] >> (i % 32)) & 1) point_j_add(&curr, &base);
    }
    *res = curr;
}

// Hashing Functions
__constant uint sha2_init[] = { 0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19 };
__constant uint sha2_k[] = { 0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2 };
#define sha2_s0(a) (rotate(a, 30U) ^ rotate(a, 19U) ^ rotate(a, 10U))
#define sha2_s1(a) (rotate(a, 26U) ^ rotate(a, 21U) ^ rotate(a, 7U))
#define sha2_ch(a, b, c) (c ^ (a & (b ^ c)))
#define sha2_ma(a, b, c) ((a & c) | (b & (a | c)))

void sha256_block(uint *out, uint *in) {
    uint s[8]; for(int i=0; i<8; i++) s[i]=out[i];
    for(int i=0; i<64; i++) {
        if(i>=16){ uint t1=in[(i+1)%16], t2=in[(i+14)%16]; in[i%16]+=in[(i+9)%16]+(rotate(t1,25U)^rotate(t1,14U)^(t1>>3))+(rotate(t2,15U)^rotate(t2,13U)^(t2>>10)); }
        uint t1=s[7]+sha2_s1(s[4])+sha2_ch(s[4],s[5],s[6])+sha2_k[i]+in[i%16], t2=sha2_s0(s[0])+sha2_ma(s[0],s[1],s[2]);
        s[7]=s[6]; s[6]=s[5]; s[5]=s[4]; s[4]=s[3]+t1; s[3]=s[2]; s[2]=s[1]; s[1]=s[0]; s[0]=t1+t2;
    }
    for(int i=0; i<8; i++) out[i]+=s[i];
}

__constant uint r_iv[]={0x67452301,0xefcdab89,0x98badcfe,0x10325476,0xc3d2e1f0}, r_k[]={0,0x5a827999,0x6ed9eba1,0x8f1bbcdc,0xa953fd4e}, r_kp[]={0x50a28be6,0x5c4dd124,0x6d703ef3,0x7a6d76e9,0};
__constant uchar r_ws[]={0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13}, r_wsp[]={5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11};
__constant uchar r_rl[] = {11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6};
__constant uchar r_rlp[] = {8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11};
uint rf(int i,uint x,uint y,uint z){if(i<16)return x^y^z;if(i<32)return(x&y)|(~x&z);if(i<48)return(x|~y)^z;if(i<64)return(x&z)|(y&~z);return x^(y|~z);}
uint rfp(int i,uint x,uint y,uint z){if(i<16)return x^(y|~z);if(i<32)return(x&z)|(y&~z);if(i<48)return(x|~y)^z;if(i<64)return(x&y)|(~x&z);return x^y^z;}
void ripemd160_block(uint *out, uint *in) {
    uint v[10]; for(int i=0; i<5; i++) v[i]=v[i+5]=out[i];
    for(int i=0; i<80; i++) {
        uint t=rotate(v[0]+rf(i,v[1],v[2],v[3])+in[r_ws[i]]+r_k[i/16],(uint)r_rl[i])+v[4]; v[0]=v[4];v[4]=v[3];v[3]=rotate(v[2],10U);v[2]=v[1];v[1]=t;
        t=rotate(v[5]+rfp(i,v[6],v[7],v[8])+in[r_wsp[i]]+r_kp[i/16],(uint)r_rlp[i])+v[9]; v[5]=v[9];v[9]=v[8];v[8]=rotate(v[7],10U);v[7]=v[6];v[6]=t;
    }
    uint t=out[1]+v[2]+v[8]; out[1]=out[2]+v[3]+v[9]; out[2]=out[3]+v[4]+v[5]; out[3]=out[4]+v[0]+v[6]; out[4]=v[0]+v[1]+v[7]; out[0]=t;
}

void hash160_compute(uchar* input, uint len, uchar* output) {
    uint h[8]; for(int i=0; i<8; i++) h[i]=sha2_init[i];
    uint w[16]={0}; for(int i=0; i<len; i++) ((uchar*)w)[i^3]=input[i]; ((uchar*)w)[len^3]=0x80; w[15]=len*8;
    sha256_block(h,w); for(int i=0; i<8; i++) h[i]=bswap32(h[i]);
    uint rh[5]; for(int i=0; i<5; i++) rh[i]=r_iv[i];
    uint rw[16]={0}; for(int i=0; i<8; i++) rw[i]=h[i]; rw[8]=0x80; rw[14]=32*8;
    ripemd160_block(rh,rw); for(int i=0; i<5; i++) { output[i*4]=rh[i]&0xff; output[i*4+1]=(rh[i]>>8)&0xff; output[i*4+2]=(rh[i]>>16)&0xff; output[i*4+3]=(rh[i]>>24)&0xff; }
}

int base58_encode_local(uchar* hash20, uchar version, char* output) {
    uchar v[21]; v[0]=version; for(int i=0; i<20; i++) v[i+1]=hash20[i];
    int z=0; while(z<21 && v[z]==0) z++;
    char buf[40]; int p=38; buf[39]=0; int s=z;
    while(s<21){ uint r=0; for(int i=s; i<21; i++){ uint t=(r<<8)+v[i]; v[i]=t/58; r=t%58; } buf[p--]=BASE58_CHARS[r]; while(s<21 && v[s]==0) s++; }
    while(z--) buf[p--]=BASE58_CHARS[0];
    int len=38-p; for(int i=0; i<len; i++) output[i]=buf[p+1+i]; output[len]=0; return len;
}

// Bloom & Binary Search
bool bloom_might_contain(__global uchar* f, uint s, uchar* h) {
    uint bits = s*8; for(uint i=0; i<7; i++) { uint idx = ( ((uint*)h)[0] ^ (i*0x9e3779b9) ) % bits; if(!(f[idx/8] & (1<<(idx%8)))) return false; }
    return true;
}
int binary_search_hash160(__global uchar* a, uint n, uchar* t) {
    int l=0, r=(int)n-1; while(l<=r){ int m=l+(r-l)/2; __global uchar* h=a+m*20; int c=0; for(int i=0; i<20; i++){ if(t[i]<h[i]){c=-1;break;} if(t[i]>h[i]){c=1;break;} } if(c==0) return 1; if(c<0) r=m-1; else l=m+1; }
    return 0;
}

// Kernels
__kernel void generate_addresses_full(__global uchar* found, __global int* count, unsigned long seed, uint batch, __global char* prefix, int prefix_len, uint max_addr, __global uchar* bloom, uint filter_size, uint check_balance) {
    int gid = get_global_id(0); if (gid >= batch) return;
    unsigned int st = (uint)seed ^ gid; bignum k; for (int i=0; i<8; i++) { st = st*1103515245+12345; uint s=st; s^=s<<13; s^=s>>17; s^=s<<5; k.d[i]=s; }
    point_j res; scalar_mult_g(&res, &k);
    if (res.z.d[0]==0 && res.z.d[1]==0 && res.z.d[2]==0 && res.z.d[3]==0 && res.z.d[4]==0 && res.z.d[5]==0 && res.z.d[6]==0 && res.z.d[7]==0) return;
    bignum zinv, zinv2, x, y, tmp; bn_from_mont(&tmp, &res.z); bn_mod_inverse(&zinv, &tmp); bn_to_mont(&zinv, &zinv);
    bn_mul_mont(&zinv2, &zinv, &zinv); bn_mul_mont(&tmp, &res.x, &zinv2); bn_from_mont(&x, &tmp);
    bn_mul_mont(&zinv2, &zinv2, &zinv); bn_mul_mont(&tmp, &res.y, &zinv2); bn_from_mont(&y, &tmp);
    uchar pubkey[33]; pubkey[0] = (y.d[0] & 1) ? 0x03 : 0x02;
    for(int i=0; i<32; i++) pubkey[32-i] = (x.d[i/4] >> ((i%4)*8)) & 0xff;
    uchar h160[20]; hash160_compute(pubkey, 33, h160);
    char addr[64]; base58_encode_local(h160, 0, addr);
    bool match = false; if(prefix_len > 0) { match=true; for(int i=0; i<prefix_len; i++) if(addr[i]!=prefix[i]) {match=false; break;} }
    if(check_balance && bloom && filter_size > 0) { if(bloom_might_contain(bloom, filter_size, h160)) match=true; }
    if(match) { int idx = atomic_inc(count); if(idx < (int)max_addr) { __global uchar* d = found + idx*128; for(int i=0; i<32; i++) d[i] = (k.d[i/4] >> ((i%4)*8)) & 0xff; for(int i=0; i<64; i++){ d[32+i]=addr[i]; if(addr[i]==0) break; } d[96]=(check_balance && bloom && bloom_might_contain(bloom, filter_size, h160))?1:0; } }
}

__kernel void generate_addresses_full_exact(__global uchar* found, __global int* count, unsigned long seed, uint batch, __global char* prefix, int prefix_len, uint max_addr, __global uchar* addr_list, uint list_count, uint check_addr) {
    int gid = get_global_id(0); if (gid >= batch) return;
    unsigned int st = (uint)seed ^ gid; bignum k; for (int i=0; i<8; i++) { st = st*1103515245+12345; uint s=st; s^=s<<13; s^=s>>17; s^=s<<5; k.d[i]=s; }
    point_j res; scalar_mult_g(&res, &k);
    if (res.z.d[0]==0 && res.z.d[1]==0 && res.z.d[2]==0 && res.z.d[3]==0 && res.z.d[4]==0 && res.z.d[5]==0 && res.z.d[6]==0 && res.z.d[7]==0) return;
    bignum zinv, zinv2, x, y, tmp; bn_from_mont(&tmp, &res.z); bn_mod_inverse(&zinv, &tmp); bn_to_mont(&zinv, &zinv);
    bn_mul_mont(&zinv2, &zinv, &zinv); bn_mul_mont(&tmp, &res.x, &zinv2); bn_from_mont(&x, &tmp);
    bn_mul_mont(&zinv2, &zinv2, &zinv); bn_mul_mont(&tmp, &res.y, &zinv2); bn_from_mont(&y, &tmp);
    uchar pubkey[33]; pubkey[0] = (y.d[0] & 1) ? 0x03 : 0x02;
    for(int i=0; i<32; i++) pubkey[32-i] = (x.d[i/4] >> ((i%4)*8)) & 0xff;
    uchar h160[20]; hash160_compute(pubkey, 33, h160);
    char addr[64]; base58_encode_local(h160, 0, addr);
    bool match = false; if(prefix_len > 0) { match=true; for(int i=0; i<prefix_len; i++) if(addr[i]!=prefix[i]) {match=false; break;} }
    bool funded = (check_addr && addr_list && list_count > 0 && binary_search_hash160(addr_list, list_count, h160));
    if(match || funded) { int idx = atomic_inc(count); if(idx < (int)max_addr) { __global uchar* d = found + idx*128; for(int i=0; i<32; i++) d[i] = (k.d[i/4] >> ((i%4)*8)) & 0xff; for(int i=0; i<64; i++){ d[32+i]=addr[i]; if(addr[i]==0) break; } d[96]=funded?1:0; } }
}

__kernel void generate_private_keys(__global uint* out, unsigned long seed, uint batch) {
    int gid = get_global_id(0); if (gid >= batch) return;
    unsigned int st = (uint)seed ^ gid; for (int i=0; i<8; i++) { st = st*1103515245+12345; uint s=st; s^=s<<13; s^=s>>17; s^=s<<5; out[gid*8+i]=s; }
}

__kernel void generate_and_check(__global uint* keys, __global char* found_addr, __global int* count, unsigned long seed, uint batch, __global uchar* bloom, uint filter_size, __global char* prefix, int prefix_len, __global char* addr_buf, uint max_addr) {
    int gid = get_global_id(0); if (gid >= batch) return;
    unsigned int st = (uint)seed ^ gid; bignum k; for (int i=0; i<8; i++) { st = st*1103515245+12345; uint s=st; s^=s<<13; s^=s>>17; s^=s<<5; k.d[i]=s; keys[gid*8+i]=s; }
    point_j res; scalar_mult_g(&res, &k);
    if (res.z.d[0]==0 && res.z.d[1]==0 && res.z.d[2]==0 && res.z.d[3]==0 && res.z.d[4]==0 && res.z.d[5]==0 && res.z.d[6]==0 && res.z.d[7]==0) return;
    bignum zinv, zinv2, x, y, tmp; bn_from_mont(&tmp, &res.z); bn_mod_inverse(&zinv, &tmp); bn_to_mont(&zinv, &zinv);
    bn_mul_mont(&zinv2, &zinv, &zinv); bn_mul_mont(&tmp, &res.x, &zinv2); bn_from_mont(&x, &tmp);
    bn_mul_mont(&zinv2, &zinv2, &zinv); bn_mul_mont(&tmp, &res.y, &zinv2); bn_from_mont(&y, &tmp);
    uchar pubkey[33]; pubkey[0] = (y.d[0] & 1) ? 0x03 : 0x02;
    for(int i=0; i<32; i++) pubkey[32-i] = (x.d[i/4] >> ((i%4)*8)) & 0xff;
    uchar h160[20]; hash160_compute(pubkey, 33, h160);
    char addr[64]; base58_encode_local(h160, 0, addr);
    bool prefix_match = false; if(prefix_len > 0) { prefix_match=true; for(int i=0; i<prefix_len; i++) if(addr[i]!=prefix[i]) {prefix_match=false; break;} }
    bool might_be_funded = (bloom && filter_size > 0 && bloom_might_contain(bloom, filter_size, h160));
    if(prefix_match || might_be_funded) { int idx = atomic_inc(count); if(idx < (int)max_addr) { __global uint* kd = (__global uint*)(addr_buf + idx*64); for(int i=0; i<8; i++) kd[i]=k.d[i]; __global char* ad = addr_buf + idx*64 + 32; for(int i=0; i<31; i++){ ad[i]=addr[i]; if(addr[i]==0) break; } ad[31]=0; } }
}
