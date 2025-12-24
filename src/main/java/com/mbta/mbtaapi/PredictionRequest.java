package com.mbta.mbtaapi;

import java.util.Set;

public class PredictionRequest {
    public String stopId;
    public Set<String> routes;
    public Integer direction;
    public Integer limit;

    public PredictionRequest() {}
}
