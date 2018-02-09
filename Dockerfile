FROM secoresearch/fuseki

ENV PATH "$PATH:/jena-fuseki/bin"

COPY mmm-sdbm-assembler.ttl /fuseki-base/configuration/assembler.ttl

RUN mkdir -p /fuseki-base/databases/tdb \
    /fuseki-base/databases/lucene \
    /fuseki-base/databases/spatiallucene

WORKDIR /jena-fuseki

ENV ASSEMBLER "/fuseki-base/configuration/assembler.ttl"
ENV TEMPDIR "/tmp/fuseki-base/databases"
ENV JAVA_CMD java -cp "$FUSEKI_HOME/fuseki-server.jar:/javalibs/*"
ENV TDBLOADER $JAVA_CMD tdb.tdbloader --desc=$ASSEMBLER

COPY --chown=9008 output.ttl /tmp/output.ttl

# Data
RUN $TDBLOADER --graph=http://ldf.fi/mmm-sdbm/ /tmp/output.ttl \
    && $JAVA_CMD jena.textindexer --desc=$ASSEMBLER \
    && $JAVA_CMD jena.spatialindexer --desc=$ASSEMBLER \
    && $JAVA_CMD tdb.tdbstats --desc=$ASSEMBLER --graph urn:x-arq:UnionGraph > /tmp/stats.opt \
    && mv /tmp/stats.opt /fuseki-base/databases/tdb/ \
    && rm /tmp/*	

VOLUME /fuseki-base/databases

EXPOSE 3030
USER 9008

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["java", "-cp", "*:/javalibs/*", "org.apache.jena.fuseki.cmd.FusekiCmd"]
