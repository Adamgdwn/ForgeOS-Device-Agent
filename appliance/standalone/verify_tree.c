/* On-device migration verifier. Compare without exporting names or contents. */
#define _GNU_SOURCE
#include <dirent.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
static uint64_t entries,bytes;
static int compare(const char *a,const char *b,unsigned depth) {
    struct stat x,y;
    if(depth>64||lstat(a,&x)||lstat(b,&y)||x.st_mode!=y.st_mode||
       x.st_uid!=y.st_uid||x.st_gid!=y.st_gid)return -1;
    entries++;
    if(S_ISDIR(x.st_mode)) {
        DIR *d=opendir(a),*e=opendir(b);
        if(!d||!e){if(d)closedir(d);if(e)closedir(e);return -1;}
        struct dirent *v;size_t na=0,nb=0;int result=0;
        while((v=readdir(d))) {
            if(!strcmp(v->d_name,".")||!strcmp(v->d_name,".."))continue;
            na++;char *p=NULL,*q=NULL;
            if(asprintf(&p,"%s/%s",a,v->d_name)<0||asprintf(&q,"%s/%s",b,v->d_name)<0||
               compare(p,q,depth+1))result=-1;
            free(p);free(q);if(result)break;
        }
        while((v=readdir(e)))if(strcmp(v->d_name,".")&&strcmp(v->d_name,".."))nb++;
        closedir(d);closedir(e);return result||na!=nb?-1:0;
    }
    if(S_ISLNK(x.st_mode)) {
        char p[4096],q[4096];ssize_t n=readlink(a,p,sizeof p),m=readlink(b,q,sizeof q);
        return n<0||m!=n||n==(ssize_t)sizeof p||memcmp(p,q,(size_t)n)?-1:0;
    }
    if(S_ISREG(x.st_mode)) {
        if(x.st_size!=y.st_size)return -1;
        int p=open(a,O_RDONLY|O_NOFOLLOW),q=open(b,O_RDONLY|O_NOFOLLOW);
        if(p<0||q<0){if(p>=0)close(p);if(q>=0)close(q);return -1;}
        char u[32768],v[32768];ssize_t n,m;int result=0;
        do {n=read(p,u,sizeof u);m=read(q,v,sizeof v);
            if(n<0||m!=n||(n>0&&memcmp(u,v,(size_t)n))){result=-1;break;}
            bytes+=(uint64_t)n;
        }while(n);
        close(p);close(q);return result;
    }
    return x.st_rdev==y.st_rdev?0:-1;
}
int main(int argc,char **argv) {
    if(argc!=3)return 64;
    if(compare(argv[1],argv[2],0)){puts("Tree verification FAILED");return 1;}
    printf("Tree verified: %"PRIu64" entries, %"PRIu64" bytes\n",entries,bytes);
    return 0;
}
